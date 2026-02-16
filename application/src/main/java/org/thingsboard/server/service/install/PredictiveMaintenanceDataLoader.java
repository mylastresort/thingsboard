/**
 * Copyright © 2016-2024 The Thingsboard Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.thingsboard.server.service.install;

import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;
import com.opencsv.CSVReader;
import com.opencsv.exceptions.CsvException;
import com.opencsv.exceptions.CsvValidationException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallbackWithoutResult;
import org.springframework.transaction.support.TransactionTemplate;
import org.thingsboard.common.util.JacksonUtil;
import org.thingsboard.server.common.data.AttributeScope;
import org.thingsboard.server.common.data.Device;
import org.thingsboard.server.common.data.DeviceProfile;
import org.thingsboard.server.common.data.id.DeviceId;
import org.thingsboard.server.common.data.id.TenantId;
import org.thingsboard.server.common.data.kv.AttributeKvEntry;
import org.thingsboard.server.common.data.kv.BaseAttributeKvEntry;
import org.thingsboard.server.common.data.kv.BasicTsKvEntry;
import org.thingsboard.server.common.data.kv.LongDataEntry;
import org.thingsboard.server.common.data.kv.StringDataEntry;
import org.thingsboard.server.common.data.kv.TsKvEntry;
import org.thingsboard.server.common.data.maintenance.DeviceError;
import org.thingsboard.server.common.data.maintenance.DeviceFailure;
import org.thingsboard.server.common.data.maintenance.DeviceMaintenance;
import org.thingsboard.server.dao.attributes.AttributesService;
import org.thingsboard.server.dao.device.DeviceProfileService;
import org.thingsboard.server.dao.device.DeviceService;
import org.thingsboard.server.dao.deviceerror.DeviceErrorService;
import org.thingsboard.server.dao.devicefailure.DeviceFailureService;
import org.thingsboard.server.dao.devicemaintenance.DeviceMaintenanceService;
import org.thingsboard.server.dao.tenant.TenantService;
import org.thingsboard.server.dao.timeseries.TimeseriesService;

import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.ExecutionException;

/**
 * Loads predictive maintenance sample data from CSV files into the database.
 * Updates timestamps to make the data current (within the last year).
 * Uses ThingsBoard's DeviceService for proper device creation.
 * Stores telemetry as timeseries data, but errors/failures/maintenance as
 * separate entities.
 */
@Slf4j
@Component
@Order(1) // Run before PredictiveMaintenanceStartupLoader
public class PredictiveMaintenanceDataLoader implements CommandLineRunner {
    @Autowired
    private TimeseriesService timeseriesService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private DeviceService deviceService;

    @Autowired
    private DeviceProfileService deviceProfileService;

    @Autowired
    private TenantService tenantService;

    @Autowired
    private AttributesService attributesService;

    @Autowired
    private DeviceErrorService deviceErrorService;

    @Autowired
    private DeviceFailureService deviceFailureService;

    @Autowired
    private DeviceMaintenanceService deviceMaintenanceService;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Value("${predictive-maintenance.data-path:predictive-maintenance/data}")
    private String dataPath;

    @Value("${predictive-maintenance.load-sample-data:false}")
    private boolean loadSampleData;

    @Value("${predictive-maintenance.tenant-email:tenant@thingsboard.org}")
    private String tenantEmail;

    @Value("${predictive-maintenance.machine-filter.machine-ids:}")
    private String machineIdsConfig;

    @Value("${predictive-maintenance.machine-filter.max-machines:100}")
    private int maxMachines;

    @Value("${predictive-maintenance.machine-filter.end-dates-machines:}")
    private String endDatesMachinesConfig;

    @Value("${predictive-maintenance.rollback-on-failure:true}")
    private boolean rollbackOnFailure;

    @Value("${predictive-maintenance.exit-on-failure:true}")
    private boolean exitOnFailure;

    @Value("${predictive-maintenance.machine-filter.end-date-machines:}")
    private String endDateMachinesConfig;

    @Value("${predictive-maintenance.load-sample-data-update-to-current-time:false}")
    private boolean updateToCurrentTime;

    private static final SimpleDateFormat DATE_FORMAT = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");

    // Track if loading is complete
    private volatile boolean loadingComplete = false;
    private volatile boolean loadingInProgress = false;

    // Filtered machine IDs to load
    private Set<Integer> allowedMachineIds = new HashSet<>();

    private Map<Integer, Date> machineEndDatesMap = new HashMap<>();

    private Map<Integer, Date> machineMaxDatesMap = new HashMap<>();

    @Override
    public void run(String... args) {
        if (!loadSampleData) {
            log.info(
                    "Predictive maintenance sample data loading is disabled. Set 'predictive-maintenance.load-sample-data=true' to enable.");
            synchronized (this) {
                loadingComplete = true;
            }
            return;
        }

        synchronized (this) {
            loadingInProgress = true;
            loadingComplete = false;
        }

        try {
            log.info("Starting predictive maintenance sample data loading...");
            log.info("Rollback on failure: {}, Exit on failure: {}", rollbackOnFailure, exitOnFailure);

            // Parse allowed machine ids and their end dates
            parseMachineFilter();

            // Should update end dates if updateToCurrentTime is set
            updateToCurrentTimestamp();

            // Check if data already exists
            if (isDataAlreadyLoaded()) {
                log.info("Predictive maintenance data already loaded. Skipping...");
                return;
            }

            Optional<TenantId> tenant = tenantService.findTenantByEmail(tenantEmail);
            log.info("Looking for tenant with email: {}", tenantEmail);
            if (!tenant.isPresent()) {
                log.error("Tenant with email {} not found", tenantEmail);
                throw new RuntimeException("Tenant with email " + tenantEmail + " not found");
            }
            log.info("Found tenant with ID: {}", tenant.get().toString());

            TenantId tenantId = tenant.get();
            if (rollbackOnFailure) {
                // Load data with transaction support and automatic rollback on failure
                TransactionTemplate transactionTemplate = new TransactionTemplate(transactionManager);
                transactionTemplate.execute(new TransactionCallbackWithoutResult() {
                    @Override
                    protected void doInTransactionWithoutResult(TransactionStatus status) {
                        try {
                            log.info("Loading data within transaction...");
                            // Load data in order: machines -> devices -> telemetry and entities
                            Map<Integer, UUID> machineToDeviceMap = loadMachinesAsDevices(tenantId);
                            loadAllData(machineToDeviceMap, tenantId);
                            log.info("Predictive maintenance sample data loaded successfully!");
                        } catch (Exception e) {
                            log.error("Error during data loading, rolling back transaction", e);
                            status.setRollbackOnly();
                            throw new RuntimeException("Failed to load predictive maintenance data", e);
                        }
                    }
                });
            } else {
                // Load data without transaction (no automatic rollback)
                log.info("Loading data without transaction support (rollback disabled)...");
                Map<Integer, UUID> machineToDeviceMap = loadMachinesAsDevices(tenantId);
                loadAllData(machineToDeviceMap, tenantId);
                log.info("Predictive maintenance sample data loaded successfully!");
            }
        } catch (Exception e) {
            log.error("Failed to load predictive maintenance sample data", e);
            if (rollbackOnFailure) {
                log.error("All database changes have been rolled back due to failure");
            }
            if (exitOnFailure) {
                log.error("Application will exit due to critical data loading failure");
                synchronized (this) {
                    loadingInProgress = false;
                    loadingComplete = true;
                    this.notifyAll();
                }
                System.exit(1); // Exit with error code
            }
        } finally {
            synchronized (this) {
                loadingInProgress = false;
                loadingComplete = true;
                this.notifyAll();
            }
        }
    }

    /**
     * Parse and validate machine filter configuration
     */
    private void parseMachineFilter() {
        if (machineIdsConfig == null || machineIdsConfig.trim().isEmpty()) {
            log.info("No machine ID list configured. Will load first {} machines (max-machines limit).", maxMachines);
            return;
        }

        String[] machineIdStrings = machineIdsConfig.split(",");
        String[] endDatesMachineStrings = null;

        // Only split end dates if config is not empty
        if (endDatesMachinesConfig != null && !endDatesMachinesConfig.trim().isEmpty()) {
            endDatesMachineStrings = endDatesMachinesConfig.split(",");
        }

        // Validate that both arrays have the same length if end dates are provided
        if (endDatesMachineStrings != null && machineIdStrings.length != endDatesMachineStrings.length) {
            String errorMsg = String.format(
                    "Machine IDs list length (%d) does not match end dates list length (%d). " +
                            "Please ensure both lists have the same number of comma-separated values.",
                    machineIdStrings.length, endDatesMachineStrings.length);
            log.error(errorMsg);
            throw new IllegalArgumentException(errorMsg);
        }

        for (int i = 0; i < machineIdStrings.length; i++) {
            String machineIdStr = machineIdStrings[i].trim();

            try {
                Integer machineId = Integer.parseInt(machineIdStr);
                allowedMachineIds.add(machineId);

                // Only parse end date if end dates config is provided
                if (endDatesMachineStrings != null) {
                    String endDateStr = endDatesMachineStrings[i].trim();
                    Date endDate = DATE_FORMAT.parse(endDateStr);
                    machineEndDatesMap.put(machineId, endDate);
                }
            } catch (NumberFormatException | ParseException e) {
                String errorMsg = "Invalid machine ID or end date in configuration: " + machineIdStr;
                if (endDatesMachineStrings != null && i < endDatesMachineStrings.length) {
                    errorMsg += ", " + endDatesMachineStrings[i].trim();
                }
                log.error(errorMsg);
                throw new IllegalArgumentException(errorMsg, e);
            }
        }

        // Validate that the number of machines doesn't exceed the maximum
        if (allowedMachineIds.size() > maxMachines) {
            String errorMsg = String.format(
                    "Number of configured machine IDs (%d) exceeds maximum allowed (%d). " +
                            "Please reduce the machine-ids list or increase max-machines setting.",
                    allowedMachineIds.size(), maxMachines);
            log.error(errorMsg);
            throw new IllegalArgumentException(errorMsg);
        }

        log.info("Machine filter configured: {} specific machines will be loaded (max allowed: {})",
                allowedMachineIds.size(), maxMachines);
        log.debug("Allowed machine IDs: {}", allowedMachineIds);
    }

    /**
     * Check if a machine ID should be loaded based on the filter
     * 
     * @param machineId   the machine ID to check
     * @param loadedCount current count of loaded machines (used for max-machines
     *                    limit)
     * @return true if machine should be loaded
     */
    private boolean shouldLoadMachine(Integer machineId, int loadedCount) {
        if (allowedMachineIds == null) {
            // No specific list configured, use max-machines limit
            return loadedCount < maxMachines;
        }
        // Specific list configured, check if machine is in the list
        return allowedMachineIds.contains(machineId);
    }

    /**
     * Check if initial loading is in progress
     */
    public boolean isLoadingInProgress() {
        return loadingInProgress;
    }

    private void updateToCurrentTimestamp() throws IOException, CsvException, ParseException {
        if (!updateToCurrentTime) {
            return;
        }

        log.info("Scanning CSV files to determine max dates for machines...");

        // Check errors file using streaming
        scanFileForMaxDates(dataPath + "/PdM_errors.csv", "errors");

        // Check failures file using streaming
        scanFileForMaxDates(dataPath + "/PdM_failures.csv", "failures");

        // Check maintenance file using streaming
        scanFileForMaxDates(dataPath + "/PdM_maint.csv", "maintenance");

        // Check telemetry file using streaming (memory-efficient for large file)
        scanFileForMaxDates(dataPath + "/PdM_telemetry.csv", "telemetry");

        log.info("Max dates scan complete. Found dates for {} machines", machineMaxDatesMap.size());
    }

    /**
     * Scan a CSV file for max dates using memory-efficient streaming (like loadTelemetryData)
     * Only processes rows for machines that need date updates
     */
    private void scanFileForMaxDates(String filePath, String fileType) throws IOException, CsvException {
        ClassPathResource resource = new ClassPathResource(filePath);

        try (CSVReader csvReader = new CSVReader(new InputStreamReader(
                resource.getInputStream(), StandardCharsets.UTF_8))) {

            // Skip header
            csvReader.readNext();

            int processedRows = 0;
            int skippedRows = 0;

            // Use iterator for memory-efficient streaming - processes one row at a time
            Iterator<String[]> iterator = csvReader.iterator();

            while (iterator.hasNext()) {
                String[] row = iterator.next();
                processedRows++;

                try {
                    Date date = DATE_FORMAT.parse(row[0]);
                    Integer machineId = Integer.parseInt(row[1]);

                    // Skip if machineId is not in allowedMachines
                    if (!allowedMachineIds.contains(machineId)) {
                        skippedRows++;
                        continue;
                    }

                    // Get configured end date if exists
                    Date configuredEndDate = machineEndDatesMap.get(machineId);

                    // Skip rows that are after the configured end date (filtering)
                    if (configuredEndDate != null && date.after(configuredEndDate)) {
                        skippedRows++;
                        continue;
                    }

                    // Store max date in machineMaxDatesMap (within the configured range)
                    if (date.after(machineMaxDatesMap.getOrDefault(machineId, new Date(0)))) {
                        machineMaxDatesMap.put(machineId, date);
                    }
                } catch (ParseException | NumberFormatException e) {
                    log.warn("Failed to parse {} row {}: {}", fileType, processedRows, e.getMessage());
                    skippedRows++;
                }
            }

            log.info("Scanned {} file: {} rows processed, {} rows skipped",
                    fileType, processedRows, skippedRows);
        }
    }

    /**
     * Wait for initial loading to complete
     */
    public void waitForLoadingComplete() throws InterruptedException {
        synchronized (this) {
            while (loadingInProgress) {
                log.info("Waiting for PredictiveMaintenanceDataLoader to complete...");
                this.wait(1000); // Wait with timeout
            }
        }
    }

    /**
     * Load all data (telemetry as timeseries, errors/failures/maintenance as
     * entities)
     * Uses concurrent saves for better performance
     */
    private void loadAllData(Map<Integer, UUID> machineToDeviceMap, TenantId tenantId)
            throws IOException, CsvException, ParseException, ExecutionException, InterruptedException {
        log.info("Loading all data...");

        // Calculate time difference ONCE at the start to ensure consistent timestamps across all data types
        Map<Integer, Long> machineTimeDiffMap = new HashMap<>();
        if (updateToCurrentTime) {
            long currentTimeMs = System.currentTimeMillis();
            for (Map.Entry<Integer, Date> entry : machineMaxDatesMap.entrySet()) {
                Integer machineId = entry.getKey();
                Date maxDate = entry.getValue();
                long timeDiff = currentTimeMs - maxDate.getTime();
                timeDiff -= timeDiff % (24 * 60 * 60 * 1000); // Round to nearest day for cleaner timestamps
                machineTimeDiffMap.put(machineId, timeDiff);
                log.debug("Machine {}: time difference = {} ms", machineId, timeDiff);
            }
        }

        // Map from deviceId to list of telemetry entries (only actual sensor readings)
        Map<UUID, List<TsKvEntry>> deviceTelemetryMap = new HashMap<>();

        // Load telemetry data (sensor readings only)
        loadTelemetryData(machineToDeviceMap, deviceTelemetryMap, machineTimeDiffMap);

        // Load errors, failures, and maintenance as separate entities (not timeseries)
        loadErrorsAsEntities(machineToDeviceMap, machineTimeDiffMap);
        loadFailuresAsEntities(machineToDeviceMap, machineTimeDiffMap);
        loadMaintenanceAsEntities(machineToDeviceMap, machineTimeDiffMap);

        // Save all telemetry for each device concurrently
        log.info("Saving timeseries data for {} devices concurrently...", deviceTelemetryMap.size());

        List<ListenableFuture<Integer>> saveFutures = new ArrayList<>();

        for (Map.Entry<UUID, List<TsKvEntry>> entry : deviceTelemetryMap.entrySet()) {
            UUID deviceId = entry.getKey();
            List<TsKvEntry> telemetryEntries = entry.getValue();
            if (!telemetryEntries.isEmpty()) {
                ListenableFuture<Integer> future = timeseriesService.save(
                        tenantId,
                        new DeviceId(deviceId),
                        telemetryEntries,
                        0L);
                saveFutures.add(future);
                log.debug("Scheduled save of {} timeseries entries for device {}",
                        telemetryEntries.size(), deviceId);
            }
        }

        // Wait for all saves to complete
        List<Integer> results = Futures.allAsList(saveFutures).get();
        log.info("Successfully saved timeseries data for {} devices", results.size());
    }

    /**
     * Load telemetry data from PdM_telemetry.csv using OpenCSV iterator for
     * memory-efficient streaming
     */
    private void loadTelemetryData(Map<Integer, UUID> machineToDeviceMap, Map<UUID, List<TsKvEntry>> deviceTelemetryMap, Map<Integer, Long> machineTimeDiffMap)
            throws IOException, ParseException, CsvValidationException {
        log.info("Loading telemetry records...");

        ClassPathResource resource = new ClassPathResource(dataPath + "/PdM_telemetry.csv");

        try (CSVReader csvReader = new CSVReader(new InputStreamReader(
                resource.getInputStream(), StandardCharsets.UTF_8))) {

            // Read header
            String[] header = csvReader.readNext();
            if (header == null) {
                log.warn("No telemetry data found in PdM_telemetry.csv");
                return;
            }

            int totalRows = 0;
            int skippedRows = 0;

            // Use iterator for memory-efficient streaming - OpenCSV processes one row at a
            // time
            Iterator<String[]> iterator = csvReader.iterator();

            while (iterator.hasNext()) {
                String[] row = iterator.next();
                totalRows++;

                try {
                    Date originalDate = DATE_FORMAT.parse(row[0]);
                    long timestamp = originalDate.getTime();
                    Integer machineId = Integer.parseInt(row[1]);
                    UUID deviceId = machineToDeviceMap.get(machineId);

                    // Efficient filtering - skip unwanted machines immediately
                    if (deviceId == null) {
                        skippedRows++;
                        continue;
                    }

                    // Get the configured end date for filtering
                    Date configuredEndDate = machineEndDatesMap.get(machineId);

                    // Skip rows where original date is AFTER the configured end date
                    if (configuredEndDate != null && originalDate.after(configuredEndDate)) {
                        skippedRows++;
                        continue;
                    }

                    if (updateToCurrentTime) {
                        // Use the pre-calculated time difference for consistent timestamps
                        Long timeDiff = machineTimeDiffMap.get(machineId);
                        if (timeDiff != null) {
                            timestamp += timeDiff;
                        }
                    }
                    // Build telemetry entries for this row
                    List<TsKvEntry> telemetryEntries = deviceTelemetryMap.computeIfAbsent(deviceId,
                            k -> new ArrayList<>());
                    for (int j = 2; j < row.length && j < header.length; j++) {
                        String key = header[j];
                        String value = row[j];
                        telemetryEntries.add(new BasicTsKvEntry(timestamp, new StringDataEntry(key, value)));
                    }
                } catch (ParseException | NumberFormatException e) {
                    log.warn("Failed to parse telemetry row {}: {}", totalRows, e.getMessage());
                    skippedRows++;
                }
            }

            log.info("Loaded {} telemetry records for {} devices (skipped {} rows for filtered machines)",
                    totalRows - skippedRows, deviceTelemetryMap.size(), skippedRows);
        }
    }

    /**
     * Load errors data from PdM_errors.csv as DeviceError entities
     */
    private void loadErrorsAsEntities(Map<Integer, UUID> machineToDeviceMap, Map<Integer, Long> machineTimeDiffMap)
            throws IOException, CsvException, ParseException {
        log.info("Loading errors as entities...");

        List<String[]> rows = readCsv(dataPath + "/PdM_errors.csv");
        int loadedCount = 0;

        for (int i = 1; i < rows.size(); i++) {
            String[] row = rows.get(i);
            Date originalDate = DATE_FORMAT.parse(row[0]);
            Timestamp timestamp = new Timestamp(originalDate.getTime());

            Integer machineId = Integer.parseInt(row[1]);
            String errorCode = row[2]; // error1, error2, error3, error4, error5

            UUID deviceId = machineToDeviceMap.get(machineId);
            if (deviceId == null)
                continue;

            // Get the configured end date for filtering
            Date configuredEndDate = machineEndDatesMap.get(machineId);

            // Skip rows where original date is AFTER the configured end date
            if (configuredEndDate != null && originalDate.after(configuredEndDate)) {
                continue;
            }

            if (updateToCurrentTime) {
                // Use the pre-calculated time difference for consistent timestamps
                Long timeDiff = machineTimeDiffMap.get(machineId);
                if (timeDiff != null) {
                    timestamp = new Timestamp(timestamp.getTime() + timeDiff);
                }
            }
            // Create DeviceError entity
            DeviceError deviceError = new DeviceError();
            deviceError.setDeviceId(new DeviceId(deviceId));
            deviceError.setErrorTime(timestamp);
            deviceError.setErrorCode(errorCode);
            deviceError.setErrorType("System Error");
            deviceError.setErrorSeverity("Warning");
            deviceError.setErrorDescription("Error code " + errorCode + " detected");
            deviceError.setWasAutoRecovered(false);
            deviceError.setLedToFailure(false);
            deviceError.setCreatedAt(new Timestamp(System.currentTimeMillis()));

            deviceErrorService.saveDeviceError(deviceError);
            loadedCount++;
        }

        log.info("Loaded {} error records as entities", loadedCount);
    }

    /**
     * Load failures data from PdM_failures.csv as DeviceFailure entities
     */
    private void loadFailuresAsEntities(Map<Integer, UUID> machineToDeviceMap, Map<Integer, Long> machineTimeDiffMap)
            throws IOException, CsvException, ParseException {
        log.info("Loading failures as entities...");

        List<String[]> rows = readCsv(dataPath + "/PdM_failures.csv");
        int loadedCount = 0;

        for (int i = 1; i < rows.size(); i++) {
            String[] row = rows.get(i);
            Date originalDate = DATE_FORMAT.parse(row[0]);
            Timestamp timestamp = new Timestamp(originalDate.getTime());

            Integer machineId = Integer.parseInt(row[1]);
            String failureComp = row[2]; // comp1, comp2, comp3, comp4

            UUID deviceId = machineToDeviceMap.get(machineId);
            if (deviceId == null)
                continue;

            // Get the configured end date for filtering
            Date configuredEndDate = machineEndDatesMap.get(machineId);

            // Skip rows where original date is AFTER the configured end date
            if (configuredEndDate != null && originalDate.after(configuredEndDate)) {
                continue;
            }

            if (updateToCurrentTime) {
                // Use the pre-calculated time difference for consistent timestamps
                Long timeDiff = machineTimeDiffMap.get(machineId);
                if (timeDiff != null) {
                    timestamp = new Timestamp(timestamp.getTime() + timeDiff);
                }
            }
            // Create DeviceFailure entity
            DeviceFailure deviceFailure = new DeviceFailure();
            deviceFailure.setDeviceId(new DeviceId(deviceId));
            deviceFailure.setFailureTime(timestamp);
            deviceFailure.setDetectionTime(timestamp); // Same as failure time in sample data
            deviceFailure.setFailureType("Component Failure");
            deviceFailure.setFailureSeverity("Critical");
            deviceFailure.setFailureDescription("Failure of " + failureComp);
            deviceFailure.setRootCause(failureComp);
            deviceFailure.setWasPredicted(false);
            deviceFailure.setCreatedAt(new Timestamp(System.currentTimeMillis()));

            deviceFailureService.saveDeviceFailure(deviceFailure);
            loadedCount++;
        }

        log.info("Loaded {} failure records as entities", loadedCount);
    }

    /**
     * Load maintenance data from PdM_maint.csv as DeviceMaintenance entities
     */
    private void loadMaintenanceAsEntities(Map<Integer, UUID> machineToDeviceMap, Map<Integer, Long> machineTimeDiffMap)
            throws IOException, CsvException, ParseException {
        log.info("Loading maintenance records as entities...");

        List<String[]> rows = readCsv(dataPath + "/PdM_maint.csv");
        int loadedCount = 0;

        for (int i = 1; i < rows.size(); i++) {
            String[] row = rows.get(i);
            Date originalDate = DATE_FORMAT.parse(row[0]);
            Timestamp timestamp = new Timestamp(originalDate.getTime());

            Integer machineId = Integer.parseInt(row[1]);
            String component = row[2]; // comp1, comp2, comp3, comp4

            UUID deviceId = machineToDeviceMap.get(machineId);
            if (deviceId == null)
                continue;

            // Get the configured end date for filtering
            Date configuredEndDate = machineEndDatesMap.get(machineId);

            // Skip rows where original date is AFTER the configured end date
            if (configuredEndDate != null && originalDate.after(configuredEndDate)) {
                continue;
            }

            if (updateToCurrentTime) {
                // Use the pre-calculated time difference for consistent timestamps
                Long timeDiff = machineTimeDiffMap.get(machineId);
                if (timeDiff != null) {
                    timestamp = new Timestamp(timestamp.getTime() + timeDiff);
                }
            }
            // Create DeviceMaintenance entity
            DeviceMaintenance deviceMaintenance = new DeviceMaintenance();
            deviceMaintenance.setDeviceId(new DeviceId(deviceId));
            deviceMaintenance.setMaintenanceType("Scheduled");
            deviceMaintenance.setMaintenanceDate(timestamp);
            deviceMaintenance.setDescription(component);
            deviceMaintenance.setCreatedAt(new Timestamp(System.currentTimeMillis()));
            deviceMaintenance.setPartsReplaced(component);

            deviceMaintenanceService.saveDeviceMaintenance(deviceMaintenance);
            loadedCount++;
        }

        log.info("Loaded {} maintenance records as entities", loadedCount);
    }

    /**
     * Check if data is already loaded to avoid duplicates
     */
    private boolean isDataAlreadyLoaded() {
        String sql = "SELECT COUNT(*) FROM device WHERE name LIKE 'PdM-Machine-%'";
        Integer count = jdbcTemplate.queryForObject(sql, Integer.class);
        return count != null && count > 0;
    }

    /**
     * Load machines as ThingsBoard devices using DeviceService
     */
    private Map<Integer, UUID> loadMachinesAsDevices(TenantId tenantId)
            throws IOException, CsvException, RuntimeException {
        log.info("Loading machines as devices...");

        List<String[]> rows = readCsv(dataPath + "/PdM_machines.csv");
        Map<Integer, UUID> machineToDeviceMap = new HashMap<>();
        int skippedCount = 0;
        int loadedCount = 0;

        for (int i = 1; i < rows.size(); i++) {
            String[] row = rows.get(i);
            Integer machineId = Integer.parseInt(row[0]);

            // Check if this machine should be loaded based on filter
            if (!shouldLoadMachine(machineId, loadedCount)) {
                skippedCount++;
                continue;
            }

            String model = row[1];
            Integer age = Integer.parseInt(row[2]);

            String deviceName = "PdM-Machine-" + machineId;
            String deviceType = "PdM-" + model;

            // Check if device already exists
            Device existingDevice = deviceService.findDeviceByTenantIdAndName(tenantId, deviceName);
            if (existingDevice != null) {
                log.debug("Device {} already exists, skipping creation", deviceName);
                machineToDeviceMap.put(machineId, existingDevice.getUuidId());
                loadedCount++;
                continue;
            }

            // Get or create device profile for this model type
            DeviceProfile deviceProfile = deviceProfileService.findOrCreateDeviceProfile(tenantId, deviceType);

            // Create new device
            Device device = new Device();
            device.setTenantId(tenantId);
            device.setName(deviceName);
            device.setType(deviceType);
            device.setLabel("Predictive Maintenance Machine " + machineId);
            device.setDeviceProfileId(deviceProfile.getId());

            // Add metadata as additional info
            ObjectNode additionalInfo = JacksonUtil.newObjectNode();
            additionalInfo.put("model", model);
            additionalInfo.put("age", age);
            additionalInfo.put("machineId", machineId);
            additionalInfo.put("description", "Predictive maintenance machine imported from sample data");
            device.setAdditionalInfo(additionalInfo);

            // Save device using ThingsBoard service
            Device savedDevice = deviceService.saveDevice(device);
            machineToDeviceMap.put(machineId, savedDevice.getUuidId());
            loadedCount++;

            // Store machine metadata as server-side attributes
            storeDeviceAttributes(tenantId, savedDevice.getId(), model, age, machineId);

            log.debug("Created device: {} (ID: {})", deviceName, savedDevice.getId());
        }

        if (skippedCount > 0) {
            log.info("Skipped {} machines due to filter configuration", skippedCount);
        }
        log.info("Loaded {} machines as devices", machineToDeviceMap.size());
        return machineToDeviceMap;
    }

    /**
     * Store device attributes using AttributesService
     */
    private void storeDeviceAttributes(TenantId tenantId, DeviceId deviceId, String model, Integer age,
            Integer machineId) {
        try {
            List<AttributeKvEntry> attributes = new ArrayList<>();
            attributes.add(new BaseAttributeKvEntry(new StringDataEntry("model", model), System.currentTimeMillis()));
            attributes.add(
                    new BaseAttributeKvEntry(new LongDataEntry("age", age.longValue()), System.currentTimeMillis()));
            attributes.add(new BaseAttributeKvEntry(new LongDataEntry("machineId", machineId.longValue()),
                    System.currentTimeMillis()));

            attributesService.save(tenantId, deviceId, AttributeScope.SERVER_SCOPE, attributes).get();
        } catch (Exception e) {
            log.error("Failed to save attributes for device {}", deviceId, e);
            throw new RuntimeException("Failed to save device attributes", e);
        }
    }

    /**
     * Read CSV file from classpath
     */
    private List<String[]> readCsv(String path) throws IOException, CsvException {
        ClassPathResource resource = new ClassPathResource(path);
        try (CSVReader reader = new CSVReader(new InputStreamReader(
                resource.getInputStream(), StandardCharsets.UTF_8))) {
            return reader.readAll();
        }
    }
}
