///
/// Copyright © 2016-2024 The Thingsboard Authors
///
/// Licensed under the Apache License, Version 2.0 (the "License");
/// you may not use this file except in compliance with the License.
/// You may obtain a copy of the License at
///
///     http://www.apache.org/licenses/LICENSE-2.0
///
/// Unless required by applicable law or agreed to in writing, software
/// distributed under the License is distributed on an "AS IS" BASIS,
/// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
/// See the License for the specific language governing permissions and
/// limitations under the License.
///

import { Injectable, NgModule } from "@angular/core";
import { RouterModule, Routes } from "@angular/router";
import { ConfigurationsListComponent } from "@app/modules/home/components/predictive-maintenance/components/configurations-list/configurations-list.component";
import { DevicesListComponent } from "@app/modules/home/components/predictive-maintenance/components/devices-list/devices-list.component";
import { DeviceModelsComponent } from "@app/modules/home/components/predictive-maintenance/components/device-models/device-models.component";
import { FailureModeComponent } from "@app/modules/home/components/predictive-maintenance/components/failure-mode/failure-mode.component";
import { OAuth2Service } from "@core/http/oauth2.service";
import { Authority } from "@shared/models/authority.enum";
import { Observable } from "rxjs";
import { RouterTabsComponent } from "../../components/router-tabs.component";
import { AgentsBenchmarkComponent } from "./agents/agents-benchmark.component";
import { AgentsIframeComponent } from "./agents/agents-iframe.component";
import { AgentsComponent } from "./agents/agents.component";
import { ModelComponent } from "./model/model.component";

@Injectable()
export class OAuth2LoginProcessingUrlResolver {
  constructor(private oauth2Service: OAuth2Service) {}

  resolve(): Observable<string> {
    return this.oauth2Service.getLoginProcessingUrl();
  }
}

const routes: Routes = [
  {
    path: "predictive-maintenance",
    component: RouterTabsComponent,
    data: {
      breadcrumb: {
        label: "Predictive Maintenance",
        icon: "mdi:cog-refresh",
      },
      useChildrenRoutesForTabs: true,
    },
    children: [
      {
        path: "",
        redirectTo: "models",
        pathMatch: "full",
      },
      {
        path: "models",
        component: ConfigurationsListComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: "predictive-maintenance.configurations",
          breadcrumb: {
            label: "Predictive Models",
            icon: "mdi:chart-timeline-variant",
          },
          isPage: true,
        },
      },
      {
        path: "failure-mode",
        component: FailureModeComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: "predictive-maintenance.failure-mode",
          breadcrumb: {
            label: "Failure Mode",
            icon: "mdi:factory",
          },
          allDevicesMode: true,
          isPage: true,
        },
      },
      {
        path: "agents",
        component: AgentsComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: "predictive-maintenance.agents",
          breadcrumb: {
            label: "Agents",
            icon: "mdi:robot-outline",
          },
          isPage: true,
        },
        children: [
          {
            path: "",
            redirectTo: "runtime",
            pathMatch: "full",
          },
          {
            path: "runtime",
            component: AgentsIframeComponent,
            data: {
              auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
              title: "predictive-maintenance.agents-runtime",
            },
          },
          {
            path: "benchmarks",
            component: AgentsBenchmarkComponent,
            data: {
              auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
              title: "predictive-maintenance.agents-benchmarks",
            },
          },
        ],
      },
      {
        path: "devices",
        component: DevicesListComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: "predictive-maintenance.devices",
          hideFromTabs: true,
          isPage: true,
        },
      },
      {
        path: "device/:deviceId/models",
        component: DeviceModelsComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: "predictive-maintenance.device-models",
          breadcrumb: {
            label: "Device Models",
            icon: "mdi:view-list",
          },
          hideFromTabs: true,
          isPage: true,
        },
      },
      {
        path: "model/:id",
        component: ModelComponent,
        data: {
          auth: [Authority.TENANT_ADMIN, Authority.CUSTOMER_USER],
          title: "predictive-maintenance.model",
          breadcrumb: {
            label: "Model",
            icon: "mdi:tools",
          },
          hideFromTabs: true,
          isPage: true,
        },
      },
    ],
  },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
  providers: [],
})
export class PredictiveMaintenanceRoutingModule {}
