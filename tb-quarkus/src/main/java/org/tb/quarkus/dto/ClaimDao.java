package org.tb.quarkus.dao;

import io.quarkus.hibernate.orm.panache.PanacheRepositoryBase;
import io.quarkus.panache.common.Page;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;
import org.tb.quarkus.entity.core.ClaimEntity;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@ApplicationScoped
public class ClaimDao implements PanacheRepositoryBase<ClaimEntity, UUID> {

    public List<ClaimEntity> findPage(UUID tenantId, Boolean done, UUID assigneeId,
                                       String textSearch, int page, int pageSize, Sort sort) {
        StringBuilder query = new StringBuilder("tenantId = ?1");
        List<Object> params = new ArrayList<>();
        params.add(tenantId);

        if (done != null) {
            query.append(" and done = ?").append(params.size() + 1);
            params.add(done);
        }
        if (assigneeId != null) {
            query.append(" and assigneeId = ?").append(params.size() + 1);
            params.add(assigneeId);
        }
        if (textSearch != null && !textSearch.isBlank()) {
            query.append(" and lower(name) like ?").append(params.size() + 1);
            params.add("%" + textSearch.toLowerCase() + "%");
        }

        return find(query.toString(), sort, params.toArray())
                .page(Page.of(page, pageSize))
                .list();
    }

    public long countPage(UUID tenantId, Boolean done, UUID assigneeId, String textSearch) {
        StringBuilder query = new StringBuilder("tenantId = ?1");
        List<Object> params = new ArrayList<>();
        params.add(tenantId);

        if (done != null) {
            query.append(" and done = ?").append(params.size() + 1);
            params.add(done);
        }
        if (assigneeId != null) {
            query.append(" and assigneeId = ?").append(params.size() + 1);
            params.add(assigneeId);
        }
        if (textSearch != null && !textSearch.isBlank()) {
            query.append(" and lower(name) like ?").append(params.size() + 1);
            params.add("%" + textSearch.toLowerCase() + "%");
        }

        return count(query.toString(), params.toArray());
    }
}