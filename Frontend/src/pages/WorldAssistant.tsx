import React, { useState, useEffect, useRef } from 'react';
import { AppShell } from '../components/AppShell';
import { useWorldStore } from '../store/useWorldStore';
import { apiFetch } from '../api/client';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string | React.ReactNode;
  citations?: { title: string; snippet: string }[];
  time: string;
}

const now = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

const greeting = (character: string | null): Message => ({
  id: `msg-intro-${Date.now()}`,
  sender: 'assistant',
  text: character
    ? `You're talking to ${character}. Ask what they would do, how they feel or what they want; they answer from what your world state says about them.`
    : 'Greetings, Chronicler. I am the Orion World Engine Assistant. Ask me about the characters, places and events in your world. Pick a character above to talk to them instead.',
  time: now(),
});

export const WorldAssistant: React.FC = () => {
  const { activeWorldId, setActiveEntity, entities, fetchEntitiesForWorld } = useWorldStore();
  // Character chat (writer's block): null talks to the world assistant, an entity id to that character
  const [focusId, setFocusId] = useState<string | null>(null);
  const characters = entities.filter((e) => e.type === 'character');
  const focus = characters.find((e) => e.id === focusId) ?? null;
  const [messages, setMessages] = useState<Message[]>(() => [greeting(null)]);
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  useEffect(() => {
    if (activeWorldId && !activeWorldId.startsWith('terra-')) fetchEntitiesForWorld(activeWorldId);
  }, [activeWorldId, fetchEntitiesForWorld]);

  const switchTo = (id: string | null) => {
    setFocusId(id);
    setMessages([greeting(characters.find((e) => e.id === id)?.name ?? null)]);
  };

  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isTyping) return;

    const userMsg: Message = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputVal('');
    setIsTyping(true);

    try {
      if (activeWorldId && !activeWorldId.startsWith('terra-')) {
        const historyPayload = messages.slice(1).slice(-8).map((m) => ({   // skip the greeting
          role: m.sender === 'user' ? 'user' : 'assistant',
          content: typeof m.text === 'string' ? m.text : ''
        }));

        const chatRes = await apiFetch<any>(`/worlds/${activeWorldId}/chat`, {
          method: 'POST',
          body: JSON.stringify({
            message: text.trim(),
            history: historyPayload,
            entity_focus: focusId
          })
        });

        const assistantMsg: Message = {
          id: `msg-${Date.now() + 1}`,
          sender: 'assistant',
          text: chatRes.response || 'I parsed your query against world lore.',
          citations: chatRes.citations || [],
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } else {
        // Fallback demo matching
        setTimeout(() => {
          let responseText: React.ReactNode = '';
          const query = text.toLowerCase();
          if (query.includes('kaelen') || query.includes('mentor')) {
            responseText = (
              <span>
                <button 
                  onClick={() => setActiveEntity('kaelen')}
                  className="text-primary hover:underline font-semibold font-headline-md"
                >
                  Kaelen
                </button>{' '}
                is a legendary archivist who withdrew from the Citadel before the Severance. According to extracted files in Chapter 2, he lives in the Undercity sub-vaults and is Elara's former mentor.
              </span>
            );
          } else if (query.includes('elara') || query.includes('vance')) {
            responseText = (
              <span>
                <button 
                  onClick={() => setActiveEntity('elara-vance')}
                  className="text-primary hover:underline font-semibold font-headline-md"
                >
                  Elara Vance
                </button>{' '}
                is the protagonist of your chronicle. Extracted records show she fled the Ashen Wastes and has a strong affinity for precursor pattern matching.
              </span>
            );
          } else {
            responseText = `I have parsed your manuscripts and indexed 5 major characters and 3 key locations. I'm ready to answer specific inquiries about your world lore.`;
          }

          setMessages((prev) => [...prev, {
            id: `msg-${Date.now() + 1}`,
            sender: 'assistant',
            text: responseText,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }]);
        }, 1000);
      }
    } catch (e: any) {
      console.warn("Chat assistant error", e);
      setMessages((prev) => [...prev, {
        id: `msg-${Date.now() + 1}`,
        sender: 'assistant',
        text: `The chat could not be reached (${e?.message ?? 'network error'}). Is the backend running?`,
        time: now()
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const presetQueries = focus
    ? [`What would you do next, ${focus.name}?`, 'How do you feel right now?', 'What do you want most?']
    : ['Who are the main characters?', 'Summarise what has happened so far.', 'How are the characters connected?'];

  return (
    <AppShell>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,rgba(230,162,126,0.02),transparent_60%)] -z-10 pointer-events-none"></div>

      <main className="flex-1 h-full min-w-0 flex flex-col relative overflow-hidden bg-surface">
        
        {/* Assistant Header */}
        <header className="h-16 border-b border-starlight-white/5 bg-surface-container-lowest/50 backdrop-blur px-8 flex items-center justify-between z-10 select-none">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full border border-primary/20 bg-primary/10 flex items-center justify-center">
              <span className="material-symbols-outlined text-primary text-lg font-light">chat_bubble_outline</span>
            </div>
            <div>
              <h2 className="font-headline-md text-sm text-starlight-white font-semibold">
                {focus ? `Talking to ${focus.name}` : 'Orion Assistant'}
              </h2>
              <p className="text-[10px] font-label-sm text-on-surface-variant/45 uppercase tracking-wider mt-0.5">
                {focus ? 'Character chat · answers from your world state' : 'Character dialogue · Grounded in your accepted world state'}
              </p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-[10px] font-label-sm text-on-surface-variant/60 uppercase tracking-wider">
            Talk to
            <select
              value={focusId ?? ''}
              onChange={(e) => switchTo(e.target.value || null)}
              disabled={isTyping}
              className="bg-surface-container-lowest border border-starlight-white/10 rounded-full px-3 py-1 text-xs normal-case tracking-normal text-starlight-white focus:border-primary focus:outline-none"
            >
              <option value="">Orion (whole world)</option>
              {characters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        </header>

        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto px-8 py-10 space-y-6 select-text scrollbar-hide">
          <div className="max-w-3xl mx-auto flex flex-col gap-6">
            
            {messages.map((msg) => {
              const isAssistant = msg.sender === 'assistant';
              return (
                <div 
                  key={msg.id}
                  className={`flex gap-4 max-w-[80%] animate-fade-in-up ${
                    isAssistant ? 'self-start' : 'self-end flex-row-reverse text-right'
                  }`}
                >
                  <div className={`w-8 h-8 rounded-full border shrink-0 flex items-center justify-center text-sm ${
                    isAssistant 
                      ? 'bg-primary/10 border-primary/20 text-primary' 
                      : 'bg-surface-container-highest border-starlight-white/10 text-starlight-white'
                  }`}>
                    <span className="material-symbols-outlined text-[16px] font-light">
                      {isAssistant ? 'bubble_chart' : 'person'}
                    </span>
                  </div>

                  <div className={`rounded-xl p-4 border text-xs leading-relaxed ${
                    isAssistant 
                      ? 'bg-surface-container-low/50 border-starlight-white/5 text-on-surface-variant' 
                      : 'bg-primary/5 border-primary/20 text-starlight-white'
                  }`}>
                    <p>{msg.text}</p>

                    {/* Citations if returned */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="mt-3 pt-2 border-t border-starlight-white/10 text-[10px] font-label-sm text-copper-glow">
                        <span className="uppercase tracking-wider font-semibold block mb-1">Citations:</span>
                        {msg.citations.map((c, i) => (
                          <div key={i} className="italic text-on-surface-variant/70">
                            • {c.title}: "{c.snippet}"
                          </div>
                        ))}
                      </div>
                    )}

                    <span className="block text-[9px] text-on-surface-variant/30 mt-2 font-label-sm uppercase tracking-wider">
                      {msg.time}
                    </span>
                  </div>
                </div>
              );
            })}

            {isTyping && (
              <div className="flex gap-4 self-start max-w-[80%]">
                <div className="w-8 h-8 rounded-full border border-primary/20 bg-primary/10 flex items-center justify-center text-primary text-sm shrink-0">
                  <span className="material-symbols-outlined text-[16px] font-light">bubble_chart</span>
                </div>
                <div className="rounded-xl p-4 bg-surface-container-low/50 border border-starlight-white/5 flex gap-1.5 items-center justify-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-primary/40 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
            
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Bar & Presets */}
        <footer className="p-6 border-t border-starlight-white/5 bg-void-black/85 backdrop-blur z-10 select-none">
          <div className="max-w-3xl mx-auto flex flex-col gap-4">
            
            {messages.length === 1 && (
              <div className="flex flex-wrap gap-2 animate-fade-in-up">
                {presetQueries.map((query, idx) => (
                  <button 
                    key={idx}
                    disabled={isTyping} onClick={() => handleSendMessage(query)}
                    className="px-3.5 py-1.5 rounded-full border border-starlight-white/10 bg-surface-container-low/20 hover:border-primary/50 text-xs text-on-surface-variant hover:text-primary transition-all font-label-sm uppercase tracking-wider text-[10px]"
                  >
                    {query}
                  </button>
                ))}
              </div>
            )}

            <form 
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage(inputVal);
              }}
              className="relative flex items-center"
            >
              <input 
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                placeholder={focus ? `Ask ${focus.name} what they would do...` : 'Ask Orion about your manuscripts...'}
                className="w-full bg-surface-container-lowest border border-starlight-white/10 rounded-full pl-6 pr-14 py-3 text-xs text-on-surface placeholder:text-on-surface-variant/30 focus:border-primary focus:ring-0 focus:outline-none"
              />
              <button 
                type="submit" disabled={isTyping || !inputVal.trim()}
                className="absolute right-2 w-9 h-9 rounded-full bg-primary hover:bg-copper-glow flex items-center justify-center text-void-black transition-colors"
                title="Send query"
              >
                <span className="material-symbols-outlined text-lg font-light">arrow_forward</span>
              </button>
            </form>
          </div>
        </footer>

      </main>
    </AppShell>
  );
};
