package org.tb.quarkus.controller;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.tb.quarkus.api.ClaimsApi;
import org.tb.quarkus.model.*;
import org.tb.quarkus.service.ClaimService;

import java.util.UUID;

@ApplicationScoped
public class ClaimApiImpl implements ClaimsApi {

    @Inject ClaimService claimService;

    @Override
    public ClaimPageResponse getClaimsByPage(Integer pageSize, Integer page, String sortProperty,
                                              String sortOrder, String textSearch,
                                              Boolean done, UUID assigneeId) {
        return claimService.listClaims(pageSize, page, sortProperty, sortOrder, textSearch, done, assigneeId);
    }

    @Override
    public ClaimResponse createClaim(CreateClaimRequest body) {
        return claimService.createClaim(body);
    }

    @Override
    public ClaimResponse getClaim(UUID claimId) {
        return claimService.getClaim(claimId);
    }

    @Override
    public ClaimResponse updateClaim(UUID claimId, UpdateClaimRequest body) {
        return claimService.updateClaim(claimId, body);
    }

    @Override
    public DeleteClaimResponse deleteClaim(UUID claimId) {
        return claimService.deleteClaim(claimId);
    }
}