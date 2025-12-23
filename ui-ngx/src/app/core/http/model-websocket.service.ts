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

import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { AnomalyLogs, AnomalyReport } from '@home/components/predictive-maintenance/components/anomalies/anomalies.component';
import { AuthService } from '@core/auth/auth.service';


enum AnomalyStreamType {
  ANOMALY_STREAM_COMMAND = 'ANOMALY_STREAM',
  ACTIVATE_COMMAND = 'activate',
  PING_COMMAND = 'ping',
  JOB_STATUS_COMMAND = 'job_status',
  SUBSCRIBE_PREDICTIONS_COMMAND = 'subscribe_predictions',
  UNSUBSCRIBE_PREDICTIONS_COMMAND = 'unsubscribe_predictions',
  UNSUBSCRIBE_JOB_LOGS_COMMAND = 'unsubscribe_logs',
  JOB_LISTEN_COMMAND = 'job_listen',
  SUBSCRIBE_LOGS_COMMAND = 'subscribe_logs',
  RESPONSE = 'response',
}

export interface AnomalyStreamMessageLogs {
  type: 'logs';
  forecast_id?: string;
  forecastId?: string;
  message?: {
    result?: AnomalyReport[]; // Can be single or array for historical
  };
  data?: AnomalyLogs; // Can be single or array for historical
  timestamp?: string;
}

export interface AnomalyStreamMessage {
  cmdId: number;
  data?: {
    type: 'connection' | 'anomaly' | 'historical' | 'error';
    forecast_id?: string;
    message?: string;
    data?: AnomalyReport | AnomalyReport[] | AnomalyLogs; // Can be single or array for historical
    timestamp?: string;
    status?: 'pending' | 'running' | 'completed' | 'failed';
  };
  errorCode?: number;
  errorMsg?: string;
  forecastId?: string;
}

export interface AnomalyStreamSubscription {
  cmdId: number;
  forecastId: string;
  observable: Observable<AnomalyStreamMessage>;
  subject: Subject<AnomalyStreamMessage>;
}

@Injectable({
  providedIn: 'root',
})
export class ModelWebSocketService {
  private ws$: WebSocketSubject<any> | null = null;

  private cmdIdCounter = 1;

  private responses$ = new Map<AnomalyStreamType, Subject<AnomalyStreamMessage | AnomalyStreamMessageLogs>>();

  private isAuthenticated = false;

  private authToken: string | null = null;

  constructor() { }

  private onConnectCbs: Array<() => void> = [];

  /**
   * Connect to ThingsBoard WebSocket
   */
  connect(): WebSocketSubject<any> {
    if (!this.ws$ || this.ws$.closed) {
      // Use GENERAL session type which supports authCmd + cmds structure
      const wsUrl = '/api/ws/model';

      // console.log("[AnomalyStream] Connecting to:", wsUrl);

      this.ws$ = webSocket({
        url: wsUrl,
        // RxJS webSocket already handles JSON serialization by default
        // No need for custom serializer - it would cause double encoding
        openObserver: {
          next: () => {
            console.info('%c[AnomalyStream] WebSocket connection opened', 'color: #9E9E9E; font-weight: bold');
            this.authenticate();
            this.onConnectCbs.forEach((cb) => cb());
          },
        },
        closeObserver: {
          next: (event) => {
            // console.log("[AnomalyStream] WebSocket connection closed", event);
            this.isAuthenticated = false;
          },
        },
      });

      // Handle incoming messages
      this.ws$.subscribe({
        next: (message) => {
          this.handleMessage(message);
        },
        error: (error) => {
          console.error('[AnomalyStream] WebSocket error:', error);
          // console.log("[AnomalyStream] Error details:", JSON.stringify(error));
          this.isAuthenticated = false;
        },
      });
    }

    return this.ws$;
  }

  /**
   * Authenticate with the WebSocket server
   */
  private authenticate(): void {
    // Get the token from AuthService (static method)
    this.authToken = AuthService.getJwtToken();

    if (this.authToken && this.ws$) {
      console.log('[AnomalyStream] Authenticating with token...');
      // TODO: Authenticate immediately on open
      this.isAuthenticated = true;
      // console.log("[AnomalyStream] Authentication ready");
    } else {
      // console.error("[AnomalyStream] No JWT token found for authentication");
      // console.log(
      // "[AnomalyStream] AuthService.getJwtToken() returned:",
      // this.authToken
      // );
      // console.log("[AnomalyStream] Make sure you are logged in to ThingsBoard");
    }
  }

  private subscribe<T extends AnomalyStreamMessage | AnomalyStreamMessageLogs>(type: AnomalyStreamType): Observable<T> {
    if (!this.responses$.has(type)) {
      this.responses$.set(type, new Subject<T>());
    }
    return this.responses$.get(type).asObservable() as Observable<T>;
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(message: any): void {
    console.log('[ModelComponent] [handleMessage()] Received message:', message);

    switch (message.type) {
      case 'progress':
        console.log('[AnomalyStream] Progress message:', message);
        this.responses$.get(AnomalyStreamType.ACTIVATE_COMMAND)?.next(message);
        break;
      case 'complete':
        console.log('[AnomalyStream] Complete message:', message);
        this.responses$.get(AnomalyStreamType.ACTIVATE_COMMAND)?.next(message);
        break;
      case 'error':
        console.error('[AnomalyStream] Error message:', message);
        this.responses$.get(AnomalyStreamType.ACTIVATE_COMMAND)?.error(message);
        break;
      case 'logs':
        // console.log('[AnomalyStream] Log message:', message);
        this.responses$.get(AnomalyStreamType.SUBSCRIBE_LOGS_COMMAND)?.next(message);
        break;
      case 'job_status':
        this.responses$.get(AnomalyStreamType.JOB_STATUS_COMMAND)?.next(message);
        break;
      case 'prediction':
        console.log('[AnomalyStream] Prediction update:', message);
        this.responses$.get(AnomalyStreamType.SUBSCRIBE_PREDICTIONS_COMMAND)?.next(message);
        break;
      case 'response':
        this.responses$.get(AnomalyStreamType.RESPONSE)?.next(message);
        break;
      default:
        if (message.type) {
          this.responses$.get(message.type)?.next(message as AnomalyStreamMessage);
        }
        break;
    }
  }

  requestJobLogs(jobId: string): Observable<AnomalyStreamMessageLogs> {
    const cmdId = this.cmdIdCounter++;
    const cmd = {
      cmdId,
      forecastId: jobId,
      type: AnomalyStreamType.SUBSCRIBE_LOGS_COMMAND,
    };
    if (!this.isConnected()) {
      this.onConnect(() => {
        this.ws$.next(cmd);
      });
    } else {
      this.ws$.next(cmd);
    }
    return this.subscribe(AnomalyStreamType.SUBSCRIBE_LOGS_COMMAND) as Observable<AnomalyStreamMessageLogs>;
  }

  requestJobStatus(jobId: string): Observable<AnomalyStreamMessage> {
    const cmdId = this.cmdIdCounter++;
    const cmd = {
      cmdId,
      forecastId: jobId,
      type: AnomalyStreamType.JOB_STATUS_COMMAND,
    };
    if (!this.isConnected()) {
      this.onConnect(() => {
        this.ws$.next(cmd);
      });
    } else {
      this.ws$.next(cmd);
    }
    return this.subscribe(AnomalyStreamType.RESPONSE);
  }

  /**
   * Subscribe to anomaly stream for a forecast
   * @param forecastId The forecast ID to stream anomalies for
   * @param startTime Optional start time (timestamp in ms) for historical data
   * @returns Observable of anomaly stream messages
   */
  // subscribeToAnomalyStream(
  //   forecastId: string,
  //   startTime?: number
  // ): Observable<AnomalyStreamMessage> {
  //   const ws = this.connect();
  //   const cmdId = this.cmdIdCounter++;
  //
  //   // console.log(
  //   //   `[AnomalyStream] Subscribing to forecast ${forecastId} with cmdId ${cmdId}`,
  //   //   startTime
  //   //     ? `from ${new Date(startTime).toISOString()}`
  //   //     : "without time filter"
  //   // );
  //
  //   // Send subscription command with authentication in the correct format
  //   const attemptSubscription = (attempt: number = 1) => {
  //     if (this.isAuthenticated && ws && this.authToken) {
  //       // console.log(
  //       //   `[AnomalyStream] Sending subscription command (attempt ${attempt})`
  //       // );
  //       const cmd: any = {
  //         cmdId,
  //         forecastId,
  //         type: AnomalyStreamType.ANOMALY_STREAM_COMMAND,
  //       };
  //
  //       // Add time window if provided
  //       if (startTime) {
  //         cmd.startTime = startTime;
  //         // console.log(
  //         //   `[AnomalyStream] Including startTime: ${startTime} (${new Date(
  //         //     startTime
  //         //   ).toISOString()})`
  //         // );
  //       }
  //       ws.next(cmd);
  //     } else if (attempt < 5) {
  //       // console.log(
  //       //   `[AnomalyStream] Not authenticated yet, waiting... (attempt ${attempt}/5)`
  //       // );
  //       setTimeout(() => attemptSubscription(attempt + 1), 1000);
  //     } else {
  //       console.error(
  //         '[AnomalyStream] Cannot subscribe - authentication timeout'
  //       );
  //       // subject.error('Authentication timeout');
  //     }
  //   };
  //
  //   // Wait for WebSocket connection to be established
  //   setTimeout(() => attemptSubscription(), 500);
  //
  //   return this.subscribe(AnomalyStreamType.ANOMALY_STREAM_COMMAND);
  // }

  onConnect(cb: () => void): void {
    this.onConnectCbs.push(cb);
  }

  private sentActivateCommand = false;

  cleanUp() {
    this.sentActivateCommand = false;
  }

  sendActivateCommand(forecastId: string): Observable<AnomalyStreamMessage> {
    if (this.sentActivateCommand) {
      console.warn(
        '[AnomalyStream] Activate command has already been sent. Ignoring duplicate.'
      );
      return this.subscribe(AnomalyStreamType.ACTIVATE_COMMAND);
    }

    // this.sentActivateCommand = true;
    // console.log(
    //   `[AnomalyStream] Sending ACTIVATE command for forecast ${forecastId} with cmdId ${cmdId}`
    // );

    const cmd = {
      cmdId: this.cmdIdCounter++,
      forecastId,
      type: AnomalyStreamType.ACTIVATE_COMMAND,
    };
    if (!this.isConnected()) {
      this.onConnect(() => {
        this.ws$.next(cmd);
      });
    } else {
      this.ws$.next(cmd);
    }

    return this.subscribe(AnomalyStreamType.ACTIVATE_COMMAND);
  }

  unsubscribeFromLogs(forecastId: string): void {
    if (!this.isConnected()) {
      console.warn(
        '[AnomalyStream] Cannot unsubscribe from logs - not connected'
      );
      return;
    }
    const cmd = {
      cmdId: this.cmdIdCounter++,
      forecastId,
      type: AnomalyStreamType.UNSUBSCRIBE_JOB_LOGS_COMMAND,
    };
    this.ws$.next(cmd);
  }

  /**
   * Subscribe to real-time job status updates (predictions)
   * Receives updates every 2 seconds when job has new iterations
   */
  subscribeToJobStatus(forecastId: string, modelType: 'anomaly' | 'forecast' = 'anomaly'): Observable<AnomalyStreamMessage> {
    const cmdId = this.cmdIdCounter++;
    const cmd = {
      commandId: cmdId,
      type: AnomalyStreamType.JOB_STATUS_COMMAND,
      forecastId,
      data: {
        modelType
      }
    };

    if (!this.isConnected()) {
      this.onConnect(() => {
        this.ws$.next(cmd);
      });
    } else {
      this.ws$.next(cmd);
    }

    console.log('[AnomalyStream] Subscribed to job status updates for forecast:', forecastId);
    return this.subscribe(AnomalyStreamType.RESPONSE);
  }

  /**
   * Unsubscribe from real-time job status updates
   */
  unsubscribeFromJobStatus(forecastId: string, modelType: 'anomaly' | 'forecast' = 'anomaly'): void {
    if (!this.isConnected()) {
      console.warn('[AnomalyStream] Cannot unsubscribe from job status - not connected');
      return;
    }

    const cmd = {
      commandId: this.cmdIdCounter++,
      type: AnomalyStreamType.UNSUBSCRIBE_PREDICTIONS_COMMAND,
      forecastId,
      data: {
        modelType
      }
    };

    this.ws$.next(cmd);
    console.log('[AnomalyStream] Unsubscribed from job status updates for forecast:', forecastId);
  }

  /**
   * Disconnect from WebSocket and cleanup all subscriptions
   */
  disconnect(): void {
    console.log(
      '[AnomalyStream] Disconnecting and cleaning up all subscriptions'
    );

    if (this.ws$) {
      this.ws$.complete();
      this.ws$ = null;
    }

    this.isAuthenticated = false;
  }

  /**
   * Check if service is connected and authenticated
   */
  isConnected(): boolean {
    return this.ws$ !== null && !this.ws$.closed && this.isAuthenticated;
  }
}
