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

import { Injectable } from "@angular/core";
import { Observable, Subject } from "rxjs";
import { webSocket, WebSocketSubject } from "rxjs/webSocket";
import { AuthService } from "@core/auth/auth.service";
import { ActivateCommand } from "@core/event-models/ActivateCommand";
import { JobStatusCommand } from "@core/event-models/JobStatusCommand";
import { ModelStatusCommand } from "@core/event-models/ModelStatusCommand";
import { PauseJobCommand } from "@core/event-models/PauseJobCommand";
import { UnpauseJobCommand } from "@core/event-models/UnpauseJobCommand";
import { SubscribeLogsCommand } from "@core/event-models/SubscribeLogsCommand";
import { UnsubscribeLogsCommand } from "@core/event-models/UnsubscribeLogsCommand";
import { UnsubscribeModelStatusCommand } from "@core/event-models/UnsubscribeModelStatusCommand";
import { UnsubscribePredictionsCommand } from "@core/event-models/UnsubscribePredictionsCommand";
import { StreamMessage } from "@core/event-models/StreamMessage";
import { StreamMessageLogs } from "@core/event-models/StreamMessageLogs";
import { ModelType } from "@core/event-models/ModelType"; // generated "anomaly" | "forecast" union — see ModelType below

export { StreamMessage };

// Internal Subject routing keys: how WE file incoming messages. Independent of the
// generated wire `type` values on purpose — renaming a wire command must never touch
// subscription routing, and vice versa.
enum ResponseTopic {
  Activate = "activate-topic",
  JobStatus = "job-status-topic",
  ModelStatus = "model-status-topic",
  Predictions = "predictions-topic",
  Logs = "logs-topic",
  Response = "response-topic",
}

/**
 * Kept as a real enum (not the generated string union) so existing call sites using
 * `ModelType.Anomaly` / `ModelType.Forecast` as values keep compiling. Values line up
 * 1:1 with the generated wire union, so a single cast at the command-building boundary
 * bridges the two — see `wireModelType()` below.
 */
export enum EModelType {
  Anomaly = "anomaly",
  Forecast = "forecast",
}

function wireModelType(modelType: EModelType): ModelType {
  return modelType as unknown as ModelType;
}

/** Closed set of commands the service will ever hand to the socket — nothing else type-checks.
 *  These are the generated wire interfaces directly; no local wrapper class needed since
 *  their shape already *is* the wire shape (commandId/type/forecastId/data). */
type KnownCommand =
  | ActivateCommand
  | JobStatusCommand
  | ModelStatusCommand
  | PauseJobCommand
  | UnpauseJobCommand
  | SubscribeLogsCommand
  | UnsubscribeLogsCommand
  | UnsubscribeModelStatusCommand
  | UnsubscribePredictionsCommand;

type IncomingSocketMessage = StreamMessage | StreamMessageLogs;

@Injectable({
  providedIn: "root",
})
export class ModelWebSocketService {
  isActivating = false;

  private ws$: WebSocketSubject<KnownCommand> | null = null;

  private cmdIdCounter = 1;

  private responses$ = new Map<
    ResponseTopic,
    Subject<StreamMessage | StreamMessageLogs>
  >();

  private isAuthenticated = false;

  private onConnectCbs: Array<() => void> = [];

  connect() {
    if (!this.ws$ || this.ws$.closed) {
      const token = AuthService.getJwtToken();
      const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${wsProtocol}://${window.location.host}/api/models/ws/unified?token=${token}`;

      this.ws$ = webSocket<KnownCommand>({
        url: wsUrl,
        serializer: (cmd) => JSON.stringify(cmd),
        openObserver: {
          next: () => {
            console.info("[AnomalyStream] WebSocket connection opened");
            this.isAuthenticated = true; // token already passed in URL
            this.onConnectCbs.forEach((cb) => cb());
            this.onConnectCbs = [];
          },
        },
        closeObserver: {
          next: () => {
            this.isAuthenticated = false;
            this.ws$ = null;
          },
        },
      });

      this.ws$.subscribe({
        // ponytail: WebSocketSubject<KnownCommand> types the outgoing send shape only —
        // rxjs's webSocket() has one generic for both directions, so incoming frames (the
        // server's raw JSON, actually IncomingSocketMessage) get typed as KnownCommand too.
        // Cast at the boundary; split webSocket's config into distinct send/receive types
        // if this ever needs to be airtight.
        next: (message) =>
          this.handleMessage(message as unknown as IncomingSocketMessage),
        error: (error) => {
          console.error("[AnomalyStream] WebSocket error:", error);
          this.isAuthenticated = false;
          this.ws$ = null;
        },
      });
    }

    return this.ws$;
  }

  onConnect(cb: () => void): void {
    this.onConnectCbs.push(cb);
  }

  isConnected(): boolean {
    return this.ws$ !== null && !this.ws$.closed && this.isAuthenticated;
  }

  disconnect(): void {
    if (this.ws$) {
      this.ws$.complete();
      this.ws$ = null;
    }
    this.isAuthenticated = false;
  }

  cleanUp() {
    // ponytail: no-op — sentActivateCommand dedup was dead code, removed.
  }

  requestJobLogs(jobId: string): Observable<StreamMessageLogs> {
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "subscribe_logs",
      forecastId: jobId,
    } satisfies SubscribeLogsCommand);
    return this.subscribe<StreamMessageLogs>(ResponseTopic.Logs);
  }

  requestJobStatus(jobId: string): Observable<StreamMessage> {
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "job_status",
      forecastId: jobId,
    } satisfies JobStatusCommand);
    // ponytail: pre-existing behavior kept — subscribes to the Response topic, not JobStatus.
    // Same mismatch in subscribeToJobStatus below. Flagging, not fixing.
    return this.subscribe<StreamMessage>(ResponseTopic.Response);
  }

  requestModelStatus(forecastId: string): Observable<StreamMessage> {
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "model_status",
      forecastId,
    } satisfies ModelStatusCommand);
    return this.subscribe<StreamMessage>(ResponseTopic.ModelStatus);
  }

  unsubscribeFromModelStatus(forecastId: string): void {
    this.sendIfConnected(
      {
        commandId: this.cmdIdCounter++,
        type: "unsubscribe_model_status",
        forecastId,
      } satisfies UnsubscribeModelStatusCommand,
      "unsubscribe from model status"
    );
  }

  sendActivateCommand(forecastId: string): Observable<StreamMessage> {
    if (!this.isConnected()) {
      this.connect();
    }
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "activate",
      forecastId,
    } satisfies ActivateCommand);
    return this.subscribe<StreamMessage>(ResponseTopic.Activate);
  }

  unsubscribeFromLogs(forecastId: string): void {
    this.sendIfConnected(
      {
        commandId: this.cmdIdCounter++,
        type: "unsubscribe_logs",
        forecastId,
      } satisfies UnsubscribeLogsCommand,
      "unsubscribe from logs"
    );
  }

  subscribeToJobStatus(
    forecastId: string,
    modelType: EModelType = EModelType.Anomaly
  ): Observable<StreamMessage> {
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "job_status",
      forecastId,
      data: { modelType: wireModelType(modelType) },
    } satisfies JobStatusCommand);
    return this.subscribe<StreamMessage>(ResponseTopic.Response);
  }

  unsubscribeFromJobStatus(
    forecastId: string,
    modelType: EModelType = EModelType.Anomaly
  ): void {
    this.sendIfConnected(
      {
        commandId: this.cmdIdCounter++,
        type: "unsubscribe_predictions",
        forecastId,
        data: { modelType: wireModelType(modelType) },
      } satisfies UnsubscribePredictionsCommand,
      "unsubscribe from job status"
    );
  }

  pauseJob(
    forecastId: string,
    modelType: EModelType = EModelType.Forecast
  ): void {
    if (!this.isConnected()) {
      this.connect();
    }
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "pause_job",
      forecastId,
      data: { modelType: wireModelType(modelType) },
    } satisfies PauseJobCommand);
  }

  unpauseJob(
    forecastId: string,
    modelType: EModelType = EModelType.Forecast
  ): void {
    if (!this.isConnected()) {
      this.connect();
    }
    this.sendOrQueue({
      commandId: this.cmdIdCounter++,
      type: "unpause_job",
      forecastId,
      data: { modelType: wireModelType(modelType) },
    } satisfies UnpauseJobCommand);
  }

  // Sends now if connected, otherwise queues for the next connection.
  private sendOrQueue(cmd: KnownCommand): void {
    if (this.isConnected()) {
      this.ws$!.next(cmd);
    } else {
      this.onConnect(() => this.ws$!.next(cmd));
    }
  }

  // Sends only if already connected; warns and drops otherwise (used for unsubscribes,
  // where queuing a cancel for a connection that doesn't exist yet makes no sense).
  private sendIfConnected(cmd: KnownCommand, action: string): void {
    if (!this.isConnected()) {
      console.warn(`[AnomalyStream] Cannot ${action} - not connected`);
      return;
    }
    this.ws$!.next(cmd);
  }

  private subscribe<T extends StreamMessage | StreamMessageLogs>(
    topic: ResponseTopic
  ): Observable<T> {
    if (!this.responses$.has(topic)) {
      this.responses$.set(
        topic,
        new Subject<StreamMessage | StreamMessageLogs>()
      );
    }
    return this.responses$.get(topic)!.asObservable() as Observable<T>;
  }

  private handleMessage(message: IncomingSocketMessage): void {
    switch (message.type) {
      case "progress":
      case "complete":
        this.responses$.get(ResponseTopic.Activate)?.next(message);
        if (message.type === "complete") this.isActivating = false;
        break;
      case "error":
        this.responses$.get(ResponseTopic.Activate)?.error(message);
        this.isActivating = false;
        break;
      case "logs":
        this.responses$.get(ResponseTopic.Logs)?.next(message);
        break;
      case "job_status":
        this.responses$.get(ResponseTopic.JobStatus)?.next(message);
        break;
      case "model_status":
        this.responses$.get(ResponseTopic.ModelStatus)?.next(message);
        break;
      case "prediction":
        this.responses$.get(ResponseTopic.Predictions)?.next(message);
        break;
      case "response":
        if (message.model === "predictive_model") {
          this.responses$.get(ResponseTopic.ModelStatus)?.next(message);
        }
        this.responses$.get(ResponseTopic.Response)?.next(message);
        break;
      default:
        // ponytail: unreachable per the exhaustive StreamMessageType/"logs" cases above, so
        // `message` narrows to `never` here — cast just to read `.type` for the warning,
        // in case a server payload ever falls outside the known vocabulary at runtime.
        console.warn(
          `[AnomalyStream] Unhandled message type: ${
            (message as { type: string }).type
          }`
        );
    }
  }
}
