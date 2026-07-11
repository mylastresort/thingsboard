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

import {
  Component,
  Input,
  OnInit,
  OnDestroy,
  OnChanges,
  SimpleChanges,
  ChangeDetectorRef,
  NgZone,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { Observable, Subscription } from 'rxjs';
import { filter, tap } from 'rxjs/operators';
import {
  trigger,
  state,
  style,
  transition,
  animate,
} from '@angular/animations';
import {
  AnomalyPrediction,
} from '../anomalies/anomalies.component';
import { GenericLogEntry as LogEntry } from '@core/event-models/GenericLogEntry';
import { AnomalyPredictionLogEntry } from '@core/event-models/AnomalyPredictionLogEntry';

export interface AnomalyAlert {
  id: string;
  timestamp: Date;
  component: string;
  probability: number;
  severity: 'Critical' | 'Major' | 'Minor';
  message: string;
  dismissed: boolean;
}

@Component({
  selector: 'tb-anomaly-alerts',
  standalone: true,
  imports: [
    CommonModule,
    MatIconModule,
    MatButtonModule,
    MatCardModule,
  ],
  templateUrl: './anomaly-alerts.component.html',
  styleUrls: ['./anomaly-alerts.component.scss'],
  host: {
    'class': 'tb-anomaly-alerts-host'
  },
  animations: [
    trigger('alertAnimation', [
      state('void', style({
        transform: 'translateX(100%)',
        opacity: 0
      })),
      state('*', style({
        transform: 'translateX(0)',
        opacity: 1
      })),
      transition(':enter', [
        animate('300ms ease-out')
      ]),
      transition(':leave', [
        animate('200ms ease-in', style({
          transform: 'translateX(100%)',
          opacity: 0
        }))
      ])
    ])
  ]
})
export class AnomalyAlertsComponent implements OnInit, OnDestroy, OnChanges {
  @Input() logsObservable!: Observable<LogEntry>;
  @Input() maxAlerts = 5; // Maximum number of stacked alerts to show
  @Input() autoCloseDelay = 10000; // Auto-close delay in milliseconds (0 = no auto-close)

  alerts: AnomalyAlert[] = [];
  private subscription!: Subscription;
  private alertIdCounter = 0;

  constructor(
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone
  ) {}

  ngOnInit(): void {
    console.log('[AnomalyAlerts] ngOnInit - logsObservable:', !!this.logsObservable);
    if (this.logsObservable) {
      this.subscribeToAnomalyPredictions();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    console.log('[AnomalyAlerts] ngOnChanges:', changes);
    if (changes.logsObservable && this.logsObservable) {
      console.log('[AnomalyAlerts] logsObservable changed, subscribing...');
      // Unsubscribe from previous subscription
      if (this.subscription) {
        this.subscription.unsubscribe();
      }
      this.subscribeToAnomalyPredictions();
    }
  }

  ngOnDestroy(): void {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
  }

  private subscribeToAnomalyPredictions(): void {
    console.log('[AnomalyAlerts] Subscribing to anomaly predictions...');
    
    if (!this.logsObservable) {
      console.error('[AnomalyAlerts] logsObservable is null/undefined!');
      return;
    }
    
    // Subscribe to ALL logs first to see what's coming through
    const allLogsSubscription = this.logsObservable.pipe(
      tap((log: LogEntry) => {
        console.log('[AnomalyAlerts] RAW LOG RECEIVED:', JSON.stringify({
          type: log.type,
          level: log.level,
          source: log.source,
          hasMessage: !!log.message,
          messageType: typeof log.message
        }));
      })
    ).subscribe();
    
    // Store for cleanup
    if (this.subscription) {
      this.subscription.unsubscribe();
    }

    const anomalyPredictionLogs$ = this.logsObservable.pipe(
      tap((log: LogEntry) => {
        console.log('[AnomalyAlerts] Checking log - type:', log.type, 'level:', log.level);
      }),
      filter((log: LogEntry) =>
        !!log.type && log.type.toLowerCase() === 'anomaly' &&
        !!log.level && log.level.toLowerCase() === 'prediction'
      )
    ) as Observable<AnomalyPredictionLogEntry>;

    this.subscription = anomalyPredictionLogs$.subscribe(log => {
      console.log('[AnomalyAlerts] Filtered anomaly prediction log:', log);
      if (typeof log.message !== 'string' && log.message?.result) {
        const results = Array.isArray(log.message.result) ? log.message.result : [log.message.result];

        results.forEach((predictionItem: AnomalyPrediction) => {
          console.log('[AnomalyAlerts] Processing prediction item:', predictionItem);
          // Only process results that predict a failure
          if (predictionItem.failure_predicted === true) {
            console.log('[AnomalyAlerts] Failure predicted! Adding alert...');
            this.ngZone.run(() => {
              this.addAlert(predictionItem);
            });
          }
        });
      }
    });
    
    console.log('[AnomalyAlerts] Subscription created successfully');
  }

  private addAlert(prediction: AnomalyPrediction): void {
    console.log('[AnomalyAlerts] addAlert called with prediction:', prediction);
    
    const probability = prediction.general_failure_probability || 0;
    const severity = this.getSeverity(probability);
    const component = prediction.predicted_failing_component || 'Unknown Component';

    const alert: AnomalyAlert = {
      id: `alert-${++this.alertIdCounter}-${Date.now()}`,
      timestamp: new Date(prediction.datetime || new Date()),
      component,
      probability,
      severity,
      message: `Failure predicted for ${component} with ${(probability * 100).toFixed(1)}% probability`,
      dismissed: false
    };

    console.log('[AnomalyAlerts] Created alert:', alert);

    // Add to the beginning of the array (newest first)
    this.alerts.unshift(alert);

    console.log('[AnomalyAlerts] Alerts array now has', this.alerts.length, 'items');

    // Limit the number of alerts
    if (this.alerts.length > this.maxAlerts) {
      this.alerts = this.alerts.slice(0, this.maxAlerts);
    }

    this.cdr.detectChanges();

    // Auto-close after delay if enabled
    if (this.autoCloseDelay > 0) {
      setTimeout(() => {
        this.dismissAlert(alert.id);
      }, this.autoCloseDelay);
    }
  }

  private getSeverity(probability: number): 'Critical' | 'Major' | 'Minor' {
    if (probability >= 0.8) {
      return 'Critical';
    } else if (probability >= 0.5) {
      return 'Major';
    }
    return 'Minor';
  }

  dismissAlert(alertId: string): void {
    const index = this.alerts.findIndex(a => a.id === alertId);
    if (index !== -1) {
      this.alerts.splice(index, 1);
      this.cdr.detectChanges();
    }
  }

  dismissAllAlerts(): void {
    this.alerts = [];
    this.cdr.detectChanges();
  }

  getSeverityColor(severity: string): string {
    switch (severity) {
      case 'Critical':
        return '#f44336'; // Red
      case 'Major':
        return '#ff9800'; // Orange
      case 'Minor':
        return '#ffeb3b'; // Yellow
      default:
        return '#2196f3'; // Blue
    }
  }

  getSeverityIcon(severity: string): string {
    switch (severity) {
      case 'Critical':
        return 'error';
      case 'Major':
        return 'warning';
      case 'Minor':
        return 'info';
      default:
        return 'notifications';
    }
  }

  formatTime(date: Date): string {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  trackByAlertId(index: number, alert: AnomalyAlert): string {
    return alert.id;
  }
}
