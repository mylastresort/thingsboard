package org.tb.quarkus.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import org.tb.quarkus.dao.ClaimDao;
import org.tb.quarkus.entity.core.ClaimEntity;
import org.tb.quarkus.model.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@ApplicationScoped
public class ClaimService {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    // TEMPORARY — replace with real tenant resolution once wired up.
    // Using your actual dev tenant from earlier logs so results line up with what you see in Swagger/UI.
    private static final UUID TEMP_TENANT_ID = UUID.fromString("ff220d60-b62d-11ef-9883-07788165022c");

    @Inject ClaimDao claimDao;

    public ClaimPageResponse listClaims(Integer pageSize, Integer page, String sortProperty,
                                         String sortOrder, String textSearch,
                                         Boolean done, UUID assigneeId) {
        UUID tenantId = TEMP_TENANT_ID;

        int size = pageSize != null ? pageSize : 10;
        int pageIdx = page != null ? page : 0;
        Sort sort = (sortProperty != null && !sortProperty.isBlank())
                ? Sort.by(sortProperty, "DESC".equalsIgnoreCase(sortOrder) ? Sort.Direction.Descending : Sort.Direction.Ascending)
                : Sort.by("createdTime", Sort.Direction.Descending);

        List<ClaimEntity> entities = claimDao.findPage(tenantId, done, assigneeId, textSearch, pageIdx, size, sort);
        long total = claimDao.countPage(tenantId, done, assigneeId, textSearch);
        int totalPages = size > 0 ? (int) Math.ceil((double) total / size) : 0;

        ClaimPageResponse response = new ClaimPageResponse();
        response.setData(entities.stream().map(this::toResponse).collect(Collectors.toList()));
        response.setTotalPages(totalPages);
        response.setTotalElements((int) total);
        response.setHasNext(pageIdx + 1 < totalPages);
        return response;
    }

    public ClaimResponse getClaim(UUID claimId) {
        ClaimEntity entity = claimDao.findByIdOptional(claimId)
                .filter(c -> c.tenantId.equals(TEMP_TENANT_ID))
                .orElseThrow(() -> new NotFoundException("Claim not found: " + claimId));
        return toResponse(entity);
    }

    @Transactional
    public ClaimResponse createClaim(CreateClaimRequest body) {
        ClaimEntity entity = new ClaimEntity();
        entity.tenantId = TEMP_TENANT_ID;
        entity.createdTime = System.currentTimeMillis();
        entity.name = body.getName();
        entity.body = body.getBody();
        entity.done = false;
        entity.assigneeId = body.getAssigneeId();
        entity.tags = body.getTags() != null ? MAPPER.valueToTree(body.getTags()) : null;
        claimDao.persist(entity);
        return toResponse(entity);
    }

    @Transactional
    public ClaimResponse updateClaim(UUID claimId, UpdateClaimRequest body) {
        ClaimEntity entity = claimDao.findByIdOptional(claimId)
                .filter(c -> c.tenantId.equals(TEMP_TENANT_ID))
                .orElseThrow(() -> new NotFoundException("Claim not found: " + claimId));

        if (body.getName() != null) entity.name = body.getName();
        if (body.getBody() != null) entity.body = body.getBody();
        if (body.getDone() != null) entity.done = body.getDone();
        if (body.getAssigneeId() != null) entity.assigneeId = body.getAssigneeId();
        if (body.getTags() != null) entity.tags = MAPPER.valueToTree(body.getTags());

        return toResponse(entity);
    }

    @Transactional
    public DeleteClaimResponse deleteClaim(UUID claimId) {
        boolean deleted = claimDao.deleteById(claimId);
        DeleteClaimResponse response = new DeleteClaimResponse();
        response.setDeletedCount(deleted ? 1 : 0);
        return response;
    }

    private ClaimResponse toResponse(ClaimEntity entity) {
        ClaimResponse response = new ClaimResponse();
        response.setId(entity.id);
        response.setCreatedTime(entity.createdTime);
        response.setName(entity.name);
        response.setBody(entity.body);
        response.setDone(entity.done);
        response.setAssigneeId(entity.assigneeId);
        response.setTags(entity.tags != null ? MAPPER.convertValue(entity.tags, Map.class) : null);
        return response;
    }
}