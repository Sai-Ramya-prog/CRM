import React, { useState, useRef, useEffect } from 'react';
import { useChat } from '../context/ChatContext';
import { useStaffAuth } from '../context/StaffAuthContext';

/**
 * Full-page AI assistant.
 *
 * Shares ChatContext with the side drawer, so a conversation started in one
 * continues in the other. The agent acts with the logged-in staff member's
 * own token, so what it can do follows their role.
 */

// Suggestions shown on an empty conversation, by role.
const SUGGESTIONS: Record<string, string[]> = {
  ADMIN: [
    'Show me the dashboard stats',
    'List all staff members',
    'Which tickets are still unassigned?',
    'How many customers do we have?',
  ],
  LEAD: [
    'Which tickets are unassigned?',
    'Show me my team',
    'What are my team stats?',
    'List my customers',
  ],
  EMPLOYEE: [
    'Show me my tickets',
    'What are my stats?',
    'Read the messages on my latest ticket',
    'Which of my tickets are still open?',
  ],
};

/** Render **bold** segments without pulling in a markdown dependency. */
const renderLine = (line: string, keyPrefix: string) => {
  const parts = line.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>
    ) : (
      <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>
    )
  );
};

const MessageBody: React.FC<{ content: string }> = ({ content }) => (
  <>
    {content.split('\n').map((line, i) => {
      const indent = line.match(/^\s*/)?.[0].length ?? 0;
      return (
        <div
          key={i}
          style={{
            paddingLeft: indent > 0 ? `${Math.min(indent, 8) * 6}px` : 0,
            minHeight: line.trim() ? undefined : '0.6em',
          }}
        >
          {renderLine(line.trimStart(), `l${i}`)}
        </div>
      );
    })}
  </>
);

const AssistantPage: React.FC = () => {
  const { messages, sendMessage, isLoading, resetChat } = useChat();
  const { user } = useStaffAuth();
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = (text: string) => {
    const message = text.trim();
    if (!message || isLoading) return;
    sendMessage(message);
    setInput('');
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  const suggestions = SUGGESTIONS[user?.role ?? 'EMPLOYEE'] ?? SUGGESTIONS.EMPLOYEE;
  const isFresh = messages.length <= 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 170px)', minHeight: 420 }}>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
          marginBottom: 18,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <h1 style={{ margin: 0 }}>AI Assistant</h1>
          <p style={{ margin: '6px 0 0', color: 'var(--muted)', fontSize: 14 }}>
            Ask about tickets, customers, orders and staff. The assistant works with your
            own permissions{user?.role ? ` as ${user.role}` : ''} — it cannot do anything you could not do yourself.
          </p>
        </div>
        <button className="btn btn-outline btn-sm" onClick={resetChat} disabled={isLoading}>
          New chat
        </button>
      </div>

      {/* Conversation */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          padding: 20,
        }}
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 14,
            }}
          >
            <div
              style={{
                maxWidth: '78%',
                padding: '12px 16px',
                borderRadius: 12,
                background: msg.role === 'user' ? 'var(--accent)' : 'var(--surface2)',
                color: msg.role === 'user' ? '#fff' : 'inherit',
                border: msg.role === 'agent' ? '1px solid var(--border)' : 'none',
                fontSize: 14,
                lineHeight: 1.55,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              <MessageBody content={msg.content} />
            </div>
          </div>
        ))}

        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 14 }}>
            <div
              style={{
                padding: '12px 16px',
                borderRadius: 12,
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                color: 'var(--muted)',
                fontSize: 14,
                fontStyle: 'italic',
              }}
            >
              Thinking…
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Suggestions on a fresh conversation */}
      {isFresh && !isLoading && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
          {suggestions.map((text) => (
            <button
              key={text}
              className="btn btn-ghost btn-sm"
              onClick={() => submit(text)}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 999,
                fontSize: 13,
                color: 'var(--muted)',
              }}
            >
              {text}
            </button>
          ))}
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
        style={{ display: 'flex', gap: 10, marginTop: 14, alignItems: 'flex-end' }}
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Ask anything about your tickets, customers or orders…"
          disabled={isLoading}
          style={{
            flex: 1,
            resize: 'none',
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid var(--border)',
            background: 'var(--surface)',
            color: 'inherit',
            fontSize: 14,
            fontFamily: 'inherit',
            lineHeight: 1.5,
          }}
        />
        <button type="submit" className="btn btn-primary" disabled={isLoading || !input.trim()}>
          Send
        </button>
      </form>

      <p style={{ margin: '8px 0 0', color: 'var(--muted)', fontSize: 12 }}>
        Enter to send, Shift+Enter for a new line. The assistant asks before anything that
        changes data.
      </p>
    </div>
  );
};

export default AssistantPage;
