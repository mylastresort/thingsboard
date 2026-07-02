///
/// Copyright © 2016-2026 The Thingsboard Authors
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

import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MarkdownService } from 'ngx-markdown';

type ChatRole = 'user' | 'assistant' | 'error';

interface ChatLine {
  id: string;
  role: ChatRole;
  text: string;
  at: string;
  html?: string;
}

interface AiAgentHealth {
  status?: string;
  ready?: boolean;
  tool_count?: number;
  error?: string;
}

interface AiAgentChatResponse {
  answer?: string;
  status?: string;
  session_id?: string | null;
}

const quickPrompts = [
  {
    label: 'Live alarms',
    query: 'show me any active alarms right now',
  },
  {
    label: 'Devices',
    query: 'which devices are online or active',
  },
  {
    label: 'Capabilities',
    query: 'what can you help me do here',
  },
  {
    label: 'Telemetry',
    query: 'help me inspect a dashboard or telemetry trend',
  },
];

function apiErrorMessage(response: Response, body: string): string {
  const text = body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  if (response.status === 504 || /504 Gateway Time-out/i.test(text)) {
    return 'ai-agent did not respond before the gateway timeout. Please try again.';
  }
  return text || `${response.status} ${response.statusText}`;
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(apiErrorMessage(response, text));
  }
  return (await response.json()) as T;
}

function newSessionId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function nowLabel(): string {
  return new Date().toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

@Component({
  selector: 'app-chatbot-overlay',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  templateUrl: './chatbot-overlay.component.html',
  styleUrls: ['./chatbot-overlay.component.scss'],
})
export class ChatbotOverlayComponent implements OnInit {
  @ViewChild('messagesBottom') messagesBottom?: ElementRef<HTMLDivElement>;

  open = false;
  loading = false;
  draft = '';
  statusText = 'Connecting to ai-agent...';
  sessionId = newSessionId();
  health: AiAgentHealth | null = null;
  messages: ChatLine[] = [];
  readonly quickPrompts = quickPrompts;

  constructor(private markdownService: MarkdownService) {}

  ngOnInit(): void {
    void this.refreshHealth();
  }

  get canSend(): boolean {
    return Boolean(this.draft.trim() && !this.loading);
  }

  toggleOpen(): void {
    this.open = !this.open;
    if (this.open) {
      this.queueScrollToBottom();
    }
  }

  resetSession(): void {
    this.sessionId = newSessionId();
    this.messages = [];
    this.statusText = 'New conversation';
    this.queueScrollToBottom();
  }

  onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void this.sendMessage();
    }
  }

  useQuickPrompt(prompt: string): void {
    this.draft = prompt;
    void this.sendMessage();
  }

  async refreshHealth(): Promise<void> {
    try {
      const next = await apiJson<AiAgentHealth>('/api/ai-agent/health');
      this.health = next;
      this.statusText = next.ready === false
        ? next.status || 'ai-agent is starting'
        : next.tool_count !== undefined
          ? `Ready · ${next.tool_count} tools`
          : next.status || 'Ready';
    } catch (error) {
      this.health = null;
      this.statusText = this.extractErrorMessage(error);
    }
  }

  async sendMessage(nextPrompt?: string): Promise<void> {
    const prompt = (nextPrompt ?? this.draft).trim();
    if (!prompt || this.loading) {
      return;
    }

    this.draft = '';
    this.loading = true;
    await this.appendMessage('user', prompt);
    this.statusText = 'Sending to ai-agent...';
    this.queueScrollToBottom();

    try {
      const response = await apiJson<AiAgentChatResponse>('/api/ai-agent/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: prompt,
          session_id: this.sessionId,
        }),
      });

      if (response.session_id) {
        this.sessionId = response.session_id;
      }

      if (response.answer) {
        await this.appendMessage('assistant', response.answer);
        this.statusText = response.status || 'Ready';
      } else {
        const message = response.status || 'ai-agent returned no answer';
        await this.appendMessage('error', message);
        this.statusText = message;
      }
    } catch (error) {
      const message = this.extractErrorMessage(error);
      await this.appendMessage('error', message);
      this.statusText = message;
    } finally {
      this.loading = false;
      this.queueScrollToBottom();
    }
  }

  private async appendMessage(role: ChatRole, text: string): Promise<void> {
    const message: ChatLine = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      role,
      text,
      at: nowLabel(),
    };

    if (role === 'assistant') {
      message.html = await Promise.resolve(this.markdownService.parse(text, {
        decodeHtml: false,
        disableSanitizer: true,
      }));
    }

    this.messages = [...this.messages, message];
  }

  private queueScrollToBottom(): void {
    queueMicrotask(() => {
      this.messagesBottom?.nativeElement.scrollIntoView({ block: 'end' });
    });
  }

  private extractErrorMessage(error: unknown): string {
    if (error instanceof Error) {
      return error.message;
    }
    return String(error);
  }
}
