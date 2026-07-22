import { useState, useRef, useEffect } from 'react';
import { Phone, PhoneOff, Mic, MicOff, Sparkles, MessageSquare, Clock, Zap, X, Minimize2, Maximize2, ChevronRight } from 'lucide-react';

interface VoiceCall {
  id: string;
  caller: string;
  phone: string;
  duration: string;
  outcome: string;
  quoteGenerated: boolean;
  quoteValue: number | null;
  date: string;
  time: string;
  transcript: string[];
}

const mockCalls: VoiceCall[] = [
  {
    id: 'call-001', caller: 'Emma Wilson', phone: '07700 900789', duration: '5m 48s', outcome: 'Quote booked — EV Charger', quoteGenerated: true, quoteValue: 2304, date: '2025-06-19', time: '10:32',
    transcript: [
      'AI: "Hello, you\'ve reached Watts Electrical. I\'m your AI assistant. How can I help?"',
      'Customer: "Hi, I need a charger for my Tesla."',
      'AI: "Great choice. For a Tesla Model 3, I\'d recommend a 7kW unit installed at £1,920 plus VAT. That includes the charger, cabling, and DNO notification."',
      'Customer: "That sounds good. When can you do it?"',
      'AI: "We have availability next Tuesday or Thursday. Would you like me to schedule a survey?"',
      'Customer: "Thursday please."',
      'AI: "Perfect. I\'ve booked you in for Thursday 25th at 10am. Your quote reference is Q-2025-0040."',
    ],
  },
  {
    id: 'call-002', caller: 'David Smith', phone: '07700 900456', duration: '3m 12s', outcome: 'Emergency callout booked', quoteGenerated: false, quoteValue: null, date: '2025-06-18', time: '08:15',
    transcript: [
      'AI: "Hello, you\'ve reached Watts Electrical. I\'m your AI assistant. How can I help?"',
      'Customer: "My power keeps tripping. Kitchen sockets are dead."',
      'AI: "That sounds like an RCD fault. I can book an emergency callout for today. Our rate is £150 callout plus £75 per hour."',
      'Customer: "Yes please, ASAP."',
      'AI: "I\'ve booked Raj for 2pm today. He\'ll bring RCBO replacements. Reference J-2025-0010."',
    ],
  },
  {
    id: 'call-003', caller: 'Sarah Johnson', phone: '07700 900123', duration: '4m 32s', outcome: 'Full rewire quote refined', quoteGenerated: true, quoteValue: 10404, date: '2025-06-15', time: '09:45',
    transcript: [
      'AI: "Hi Sarah, I see you received our quote for the full rewire at £10,404. How can I help?"',
      'Customer: "Can we add a few more downlights in the kitchen?"',
      'AI: "Adding 6 extra fire-rated LED downlights in the kitchen would be £210 plus VAT. Your revised total would be £10,656. Shall I update the quote?"',
      'Customer: "Yes, and can we start a week earlier?"',
      'AI: "Let me check... we can start June 28th. Updated quote Q-2025-0042 on its way to your email."',
    ],
  },
  {
    id: 'call-004', caller: 'Unknown', phone: '020 7946 0555', duration: '2m 08s', outcome: 'General enquiry — passed to Tom', quoteGenerated: false, quoteValue: null, date: '2025-06-17', time: '14:22',
    transcript: [
      'AI: "Hello, Watts Electrical. How can I help?"',
      'Customer: "I need a quote for a commercial building. 3-phase supply."',
      'AI: "For commercial 3-phase work, I\'ll need to pass you to Tom. He\'ll call you back within the hour. Can I take your details?"',
      'Customer: "Yes, it\'s Mark from Apex Property."',
      'AI: "Thank you Mark. Tom will call you on 020 7946 0555 shortly."',
    ],
  },
];

export function VoiceAgentWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'calls' | 'live'>('calls');
  const [selectedCall, setSelectedCall] = useState<VoiceCall | null>(null);
  const [isCallActive, setIsCallActive] = useState(false);
  const [callTimer, setCallTimer] = useState(0);
  const [isListening, setIsListening] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isCallActive) {
      timerRef.current = setInterval(() => setCallTimer(t => t + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      setCallTimer(0);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isCallActive]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-[300] w-14 h-14 rounded-full bg-[#D4650A] text-white shadow-lg hover:shadow-xl hover:scale-105 transition-all flex items-center justify-center group"
        title="Voice Agent"
        aria-label="Open Voice AI Agent"
        aria-expanded={isOpen}
      >
        <Phone className="w-6 h-6" />
        <span className="absolute -top-1 -right-1 w-4 h-4 bg-[#16A34A] rounded-full border-2 border-[#F8F7F4]" />
        <span className="absolute right-full mr-3 px-2.5 py-1.5 bg-[#1C1917] text-white text-xs font-medium rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
          Voice AI Agent
        </span>
      </button>
    );
  }

  return (
    <div className={`fixed bottom-6 right-6 z-[300] bg-white rounded-2xl border border-[#E7E5E4] shadow-xl overflow-hidden transition-all duration-300 ${isExpanded ? 'w-[480px] h-[640px]' : 'w-[380px] h-[520px]'}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#1C1917]">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${isCallActive ? 'bg-[#DC2626] animate-pulse' : 'bg-[#D4650A]'}`}>
            <Phone className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Voice AI Agent</div>
            <div className="text-[11px] text-[#A8A29E] flex items-center gap-1">
              {isCallActive ? (
                <><span className="w-1.5 h-1.5 rounded-full bg-[#DC2626]" /> Live Call — {formatTime(callTimer)}</>
              ) : (
                <><span className="w-1.5 h-1.5 rounded-full bg-[#16A34A]" /> Online — 4 calls today</>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setIsExpanded(!isExpanded)} aria-label={isExpanded ? 'Collapse' : 'Expand'} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/10 transition-colors">
            {isExpanded ? <Minimize2 className="w-3.5 h-3.5 text-[#A8A29E]" /> : <Maximize2 className="w-3.5 h-3.5 text-[#A8A29E]" />}
          </button>
          <button onClick={() => { setIsOpen(false); setSelectedCall(null); }} aria-label="Close" className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/10 transition-colors">
            <X className="w-3.5 h-3.5 text-[#A8A29E]" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      {!isCallActive && !selectedCall && (
        <div className="flex border-b border-[#F0EFEA]">
          <button onClick={() => setActiveTab('calls')} className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-[0.05em] transition-colors ${activeTab === 'calls' ? 'text-[#D4650A] border-b-2 border-[#D4650A]' : 'text-[#78716C] hover:text-[#1C1917]'}`}>
            Call Log
          </button>
          <button onClick={() => setActiveTab('live')} className={`flex-1 py-2.5 text-xs font-semibold uppercase tracking-[0.05em] transition-colors ${activeTab === 'live' ? 'text-[#D4650A] border-b-2 border-[#D4650A]' : 'text-[#78716C] hover:text-[#1C1917]'}`}>
            New Call
          </button>
        </div>
      )}

      {/* Content */}
      <div className="overflow-y-auto" style={{ height: isExpanded ? 'calc(640px - 52px - 41px)' : 'calc(520px - 52px - 41px)' }}>
        {isCallActive ? (
          <LiveCallView timer={callTimer} isListening={isListening} setIsListening={setIsListening} onEnd={() => setIsCallActive(false)} />
        ) : selectedCall ? (
          <CallDetailView call={selectedCall} onBack={() => setSelectedCall(null)} />
        ) : activeTab === 'calls' ? (
          <CallLogView calls={mockCalls} onSelect={setSelectedCall} />
        ) : (
          <NewCallView onStartCall={() => setIsCallActive(true)} />
        )}
      </div>
    </div>
  );
}

function CallLogView({ calls, onSelect }: { calls: VoiceCall[]; onSelect: (c: VoiceCall) => void }) {
  return (
    <div className="divide-y divide-[#F0EFEA]">
      {calls.map(call => (
        <button key={call.id} onClick={() => onSelect(call)} className="w-full px-4 py-3 text-left hover:bg-[#F5F4F0] transition-colors flex items-start gap-3">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${call.quoteGenerated ? 'bg-[#F5F3FF]' : 'bg-[#EFF6FF]'}`}>
            {call.quoteGenerated ? <Sparkles className="w-4 h-4 text-[#7C3AED]" /> : <Phone className="w-4 h-4 text-[#2563EB]" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-[#1C1917]">{call.caller}</span>
              <span className="text-[11px] text-[#A8A29E]">{call.time}</span>
            </div>
            <div className="text-xs text-[#78716C] mt-0.5">{call.outcome}</div>
            <div className="flex items-center gap-3 mt-1.5">
              <span className="text-[11px] text-[#A8A29E] flex items-center gap-1"><Clock className="w-3 h-3" /> {call.duration}</span>
              {call.quoteGenerated && call.quoteValue && (
                <span className="text-[11px] font-medium text-[#7C3AED] flex items-center gap-1"><Sparkles className="w-3 h-3" /> £{call.quoteValue.toLocaleString()}</span>
              )}
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-[#A8A29E] flex-shrink-0 mt-2" />
        </button>
      ))}
    </div>
  );
}

function CallDetailView({ call, onBack }: { call: VoiceCall; onBack: () => void }) {
  return (
    <div className="p-4">
      <button onClick={onBack} className="text-xs text-[#D4650A] font-medium mb-3 hover:underline">← Back to calls</button>
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-full bg-[#F5F4F0] flex items-center justify-center text-sm font-semibold text-[#57534E]">
          {call.caller[0]}
        </div>
        <div>
          <div className="text-sm font-semibold text-[#1C1917]">{call.caller}</div>
          <div className="text-xs text-[#78716C]">{call.phone}</div>
        </div>
      </div>
      <div className="flex items-center gap-4 mb-4 text-xs text-[#78716C]">
        <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {call.duration}</span>
        <span>{call.date} at {call.time}</span>
        {call.quoteGenerated && <span className="text-[#7C3AED] font-medium flex items-center gap-1"><Sparkles className="w-3.5 h-3.5" /> Quote generated</span>}
      </div>
      <h4 className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-2">Transcript</h4>
      <div className="space-y-2">
        {call.transcript.map((line, i) => (
          <div key={i} className={`text-sm p-2.5 rounded-lg ${line.startsWith('AI:') ? 'bg-[#F5F3FF] text-[#1C1917]' : 'bg-[#F5F4F0] text-[#57534E]'}`}>
            {line}
          </div>
        ))}
      </div>
    </div>
  );
}

function NewCallView({ onStartCall }: { onStartCall: () => void }) {
  return (
    <div className="p-6 flex flex-col items-center text-center">
      <div className="w-16 h-16 rounded-full bg-[#F0FDF4] flex items-center justify-center mb-4">
        <Zap className="w-8 h-8 text-[#16A34A]" />
      </div>
      <h3 className="text-base font-semibold text-[#1C1917] mb-1">Start Voice Call</h3>
      <p className="text-sm text-[#78716C] mb-6 max-w-[260px]">Simulate an inbound customer call. The AI agent will handle the conversation and generate a quote.</p>
      <button
        onClick={onStartCall}
        aria-label="Simulate inbound call"
        className="w-full h-12 rounded-xl bg-[#16A34A] text-white text-sm font-semibold hover:bg-[#15803D] transition-colors flex items-center justify-center gap-2"
      >
        <Phone className="w-5 h-5" /> Simulate Inbound Call
      </button>
      <div className="mt-6 space-y-3 w-full text-left">
        <div className="text-[11px] font-semibold uppercase tracking-[0.05em] text-[#78716C] mb-2">Capabilities</div>
        {[
          { icon: MessageSquare, text: 'Handle customer enquiries 24/7' },
          { icon: Sparkles, text: 'Generate quotes during the call' },
          { icon: Zap, text: 'Book emergency callouts instantly' },
          { icon: Phone, text: 'Refine existing quotes with customer' },
        ].map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-center gap-2.5 text-sm text-[#57534E]">
            <Icon className="w-4 h-4 text-[#D4650A]" /> {text}
          </div>
        ))}
      </div>
    </div>
  );
}

function LiveCallView({ timer, isListening, setIsListening, onEnd }: {
  timer: number; isListening: boolean; setIsListening: (v: boolean) => void; onEnd: () => void;
}) {
  const [messages, setMessages] = useState([
    { speaker: 'ai' as const, text: 'Hello, you\'ve reached Watts Electrical. I\'m your AI assistant. How can I help you today?' },
    { speaker: 'customer' as const, text: 'Hi, I\'m looking for a quote for a full rewire on my 3-bed house.' },
    { speaker: 'ai' as const, text: 'I can certainly help with that. For a 3-bedroom property, our full rewire typically starts at £8,670 plus VAT. This includes a new consumer unit, LED downlights, socket outlets, and full certification. Would you like me to generate a detailed quote?' },
  ]);

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (timer === 15) {
      setMessages(prev => [...prev, { speaker: 'customer', text: 'Yes please, that sounds good. When could you start?' }]);
    }
    if (timer === 20) {
      setMessages(prev => [...prev, { speaker: 'ai', text: 'I\'ve created quote Q-2025-0050 for £8,670 plus VAT. We have availability starting July 7th. I\'ll send this to your email now. Is there anything else I can help with?' }]);
    }
  }, [timer]);

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.speaker === 'ai' ? 'justify-start' : 'justify-end'}`}>
            <div className={`max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm ${
              msg.speaker === 'ai'
                ? 'bg-[#F5F3FF] text-[#1C1917] rounded-bl-sm'
                : 'bg-[#F5F4F0] text-[#1C1917] rounded-br-sm'
            }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {isListening && (
          <div className="flex justify-center">
            <div className="flex items-center gap-1 px-3 py-1.5 bg-[#FFF7ED] rounded-full">
              <span className="w-1.5 h-1.5 bg-[#D4650A] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-[#D4650A] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-[#D4650A] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              <span className="text-[11px] text-[#D4650A] ml-1">Listening...</span>
            </div>
          </div>
        )}
      </div>
      <div className="p-3 border-t border-[#F0EFEA] bg-[#FAFAF9]">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsListening(!isListening)}
            aria-label="Toggle microphone"
            className={`w-10 h-10 rounded-full flex items-center justify-center transition-colors ${isListening ? 'bg-[#D4650A] text-white' : 'bg-[#F5F4F0] text-[#57534E] hover:bg-[#EFEEE9]'}`}
          >
            {isListening ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
          </button>
          <div className="flex-1 text-center text-xs text-[#78716C]">{formatTime(timer)}</div>
          <button
            onClick={onEnd}
            aria-label="End call"
            className="w-10 h-10 rounded-full bg-[#DC2626] text-white flex items-center justify-center hover:bg-[#B91C1C] transition-colors"
          >
            <PhoneOff className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
