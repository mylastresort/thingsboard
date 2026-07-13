package org.tb.quarkus.controller;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.tb.quarkus.api.ApiApi;
import org.tb.quarkus.model.NotifyAlarmAssigneeRequest;
import org.tb.quarkus.model.NotifyAlarmBody;
import org.tb.quarkus.model.NotifyClaimAssigneeRequest;
import org.tb.quarkus.model.NotifySentResponse;
import org.tb.quarkus.model.NotifyStatusResponse;
import org.tb.quarkus.service.NotifyService;

@ApplicationScoped
public class NotifyApiImpl implements ApiApi {

    @Inject NotifyService notifyService;

    @Override
    public NotifyStatusResponse notifyAlarmAssignee(NotifyAlarmAssigneeRequest body) {
        return notifyService.notifyAlarmAssignee(body);
    }

    @Override
    public NotifyStatusResponse notifyClaimAssignee(NotifyClaimAssigneeRequest body) {
        return notifyService.notifyClaimAssignee(body);
    }

    @Override
    public NotifySentResponse notifyNewAlarm(NotifyAlarmBody body) {
        return notifyService.notifyNewAlarm(body);
    }
}
