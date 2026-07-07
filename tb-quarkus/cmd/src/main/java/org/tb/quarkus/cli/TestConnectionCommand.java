package org.tb.quarkus.cli;

import jakarta.inject.Inject;
import org.eclipse.microprofile.rest.client.inject.RestClient;
import org.tb.quarkus.gateway.client.api.AgenticBenchmarkApi;
import org.tb.quarkus.hf.HfDatasetClient;
import org.tb.quarkus.gateway.client.model.AgenticBenchmarkSubset;
import org.tb.quarkus.tb.TbGateway;
import picocli.CommandLine;

import java.util.List;
import java.util.concurrent.Callable;

@CommandLine.Command(
        name = "test-connection",
        mixinStandardHelpOptions = true,
        description = "Test configured ThingsBoard, HuggingFace, and tb-quarkus gateway connectivity."
)
public class TestConnectionCommand implements Callable<Integer> {

    @Inject
    TbGateway tb;

    @Inject
    HfDatasetClient hf;

    @Inject
    @RestClient
    AgenticBenchmarkApi agenticBenchmarkApi;

    @CommandLine.Option(
            names = {"--thingsboard", "--thingsboard-client", "--tb"},
            description = "Test ThingsBoard login and token-authenticated API access."
    )
    boolean thingsboard;

    @CommandLine.Option(
            names = {"--huggingface", "--huggingface-url", "--hf"},
            description = "Test HuggingFace dataset /splits and /rows endpoints."
    )
    boolean huggingFace;

    @CommandLine.Option(
            names = {"--gateway", "--tb-quarkus", "--gateway-client"},
            description = "Test tb-quarkus gateway API connectivity (agentic-benchmark endpoints)."
    )
    boolean gateway;

    @Override
    public Integer call() {
        boolean runAll = !thingsboard && !huggingFace && !gateway;
        boolean ok = true;

        if (runAll || thingsboard) {
            ok &= testThingsBoard();
        }
        if (runAll || huggingFace) {
            ok &= testHuggingFace();
        }
        if (runAll || gateway) {
            ok &= testGateway();
        }

        return ok ? 0 : 1;
    }

    private boolean testThingsBoard() {
        System.out.print("ThingsBoard: ");
        try {
            TbGateway.AuthCheck check = tb.testConnection();
            System.out.printf("OK url=%s user=%s authority=%s%n",
                    check.baseUrl(), check.username(), emptyAsUnknown(check.authority()));
            return true;
        } catch (Exception e) {
            System.out.println("FAILED " + e.getMessage());
            return false;
        }
    }

    private boolean testHuggingFace() {
        System.out.print("HuggingFace: ");
        try {
            HfDatasetClient.EndpointCheck check = hf.testEndpoints();
            System.out.printf("OK dataset=%s config=%s split=%s configs=%d sampleRows=%d totalRows=%s%n",
                    check.dataset(),
                    check.config(),
                    check.split(),
                    check.splitCount(),
                    check.sampleRows(),
                    check.totalRows() >= 0 ? Integer.toString(check.totalRows()) : "unknown");
            return true;
        } catch (Exception e) {
            System.out.println("FAILED " + e.getMessage());
            return false;
        }
    }

    private boolean testGateway() {
        System.out.print("tb-quarkus gateway: ");
        try {
            List<AgenticBenchmarkSubset> subsets = agenticBenchmarkApi.getAgenticBenchmarkSubsets()
                    .await().indefinitely();
            System.out.printf("OK subsets=%d%n", subsets == null ? 0 : subsets.size());
            return true;
        } catch (Exception e) {
            System.out.println("FAILED " + e.getMessage());
            return false;
        }
    }

    private static String emptyAsUnknown(String value) {
        return value == null || value.isBlank() ? "unknown" : value;
    }
}