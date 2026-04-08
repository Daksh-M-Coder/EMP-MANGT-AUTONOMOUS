import { useState, useRef, useEffect } from 'react';
import { api } from '../lib/api.js';
import { 
  Send, Bot, User, Loader2, CheckCircle, XCircle, 
  ChevronDown, ChevronUp, Sparkles, Lightbulb,
  FileText, Check, X, AlertCircle
} from 'lucide-react';

export default function AIChat({ onClose, embedded = false }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hello! I\'m your HR assistant. I can help you search for employees, view statistics, or assist with adding new employees. How can I help you today?' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [pendingDraft, setPendingDraft] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadSuggestions();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadSuggestions = async () => {
    try {
      const data = await api.getSuggestions();
      setSuggestions(data.slice(0, 6));
    } catch (err) {
      console.error('Failed to load suggestions:', err);
    }
  };

  const sendMessage = async (content) => {
    if (!content.trim() || loading) return;

    const userMessage = { role: 'user', content };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setShowSuggestions(false);

    try {
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      const result = await api.chat(content, history);

      // Check if result contains a draft for review
      if (result.draft_employee || (result.tool_calls && result.tool_calls.some(t => t.tool_name === 'hr_employee_add_draft'))) {
        const draftToolCall = result.tool_calls?.find(t => t.tool_name === 'hr_employee_add_draft');
        if (draftToolCall?.tool_output?.draft) {
          setPendingDraft(draftToolCall.tool_output.draft);
        }
      }

      const assistantMessage = {
        role: 'assistant',
        content: result.final_answer || result.response || 'I processed your request.',
        plan: result.plan,
        toolCalls: result.tool_calls,
        reflection: result.reflections?.[0],
        raw: result
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Sorry, I encountered an error: ${err.message}. Please try again.`
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleSuggestionClick = (suggestion) => {
    sendMessage(suggestion);
  };

  return (
    <div className={`flex flex-col bg-white ${embedded ? 'h-full' : 'h-[600px] w-[400px] rounded-lg shadow-xl border'} overflow-hidden`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-indigo-600 text-white">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5" />
          <span className="font-semibold">HR Assistant</span>
        </div>
        {onClose && (
          <button onClick={onClose} className="hover:bg-indigo-700 rounded p-1">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <MessageBubble 
            key={idx} 
            message={msg} 
            isLast={idx === messages.length - 1}
          />
        ))}

        {/* Pending Draft Review UI */}
        {pendingDraft && (
          <DraftReviewCard 
            draft={pendingDraft} 
            onApprove={(id) => {
              setPendingDraft(null);
              setMessages(prev => [...prev, {
                role: 'assistant',
                content: `✅ Employee draft has been approved and the employee has been added to the system.`
              }]);
            }}
            onReject={() => {
              setPendingDraft(null);
              setMessages(prev => [...prev, {
                role: 'assistant',
                content: `❌ Employee draft has been rejected.`
              }]);
            }}
          />
        )}

        {loading && (
          <div className="flex items-center gap-2 text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        )}

        {/* Suggestions */}
        {showSuggestions && suggestions.length > 0 && messages.length < 3 && (
          <div className="mt-4">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
              <Lightbulb className="w-4 h-4" />
              <span>Try asking:</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggestionClick(s)}
                  className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-full transition-colors text-left"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t bg-gray-50">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about employees..."
            className="flex-1 px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
      </form>
    </div>
  );
}

function MessageBubble({ message, isLast }) {
  const [expanded, setExpanded] = useState(false);
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
        isUser ? 'bg-gray-200' : 'bg-indigo-100'
      }`}>
        {isUser ? <User className="w-4 h-4 text-gray-600" /> : <Bot className="w-4 h-4 text-indigo-600" />}
      </div>

      <div className={`flex-1 max-w-[80%] ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block text-left rounded-lg px-4 py-2 ${
          isUser ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-800'
        }`}>
          <div className="prose prose-sm max-w-none">
            {message.content}
          </div>
        </div>

        {/* Plan/Tool Calls Toggle */}
        {!isUser && (message.plan || message.toolCalls) && (
          <div className="mt-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
            >
              {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {expanded ? 'Hide details' : 'Show reasoning'}
              {message.reflection && (
                <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                  message.reflection.quality_score >= 0.8 ? 'bg-green-100 text-green-700' :
                  message.reflection.quality_score >= 0.6 ? 'bg-yellow-100 text-yellow-700' :
                  'bg-red-100 text-red-700'
                }`}>
                  {Math.round(message.reflection.quality_score * 100)}%
                </span>
              )}
            </button>

            {expanded && (
              <div className="mt-2 text-left bg-gray-50 rounded p-3 text-xs space-y-2">
                {message.plan && (
                  <div>
                    <span className="font-semibold text-gray-600">Plan:</span>
                    <ul className="mt-1 space-y-1">
                      {message.plan.map((step, i) => (
                        <li key={i} className="flex items-start gap-2">
                          {step.status === 'done' ? (
                            <CheckCircle className="w-3 h-3 text-green-500 mt-0.5 shrink-0" />
                          ) : step.status === 'failed' ? (
                            <XCircle className="w-3 h-3 text-red-500 mt-0.5 shrink-0" />
                          ) : (
                            <div className="w-3 h-3 rounded-full border-2 border-gray-300 mt-0.5 shrink-0" />
                          )}
                          <span className={step.status === 'done' ? 'text-green-700' : 'text-gray-600'}>
                            {step.description}
                            {step.tool && <span className="text-gray-400"> → {step.tool}</span>}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {message.toolCalls?.length > 0 && (
                  <div>
                    <span className="font-semibold text-gray-600">Tools used:</span>
                    <div className="mt-1 space-y-1">
                      {message.toolCalls.map((call, i) => (
                        <div key={i} className="bg-white rounded p-2 border">
                          <div className="flex items-center gap-2">
                            <Sparkles className="w-3 h-3 text-indigo-500" />
                            <span className="font-medium">{call.tool_name}</span>
                            {call.success ? (
                              <Check className="w-3 h-3 text-green-500" />
                            ) : (
                              <AlertCircle className="w-3 h-3 text-red-500" />
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function DraftReviewCard({ draft, onApprove, onReject }) {
  const [reviewing, setReviewing] = useState(false);
  const [notes, setNotes] = useState('');

  const handleApprove = async () => {
    setReviewing(true);
    try {
      await api.approveDraft(draft.draft_id || draft.employee_id, notes);
      onApprove(draft.draft_id || draft.employee_id);
    } catch (err) {
      alert('Failed to approve: ' + err.message);
    } finally {
      setReviewing(false);
    }
  };

  const handleReject = async () => {
    if (!notes.trim()) {
      alert('Please provide a reason for rejection');
      return;
    }
    setReviewing(true);
    try {
      await api.rejectDraft(draft.draft_id || draft.employee_id, notes);
      onReject();
    } catch (err) {
      alert('Failed to reject: ' + err.message);
    } finally {
      setReviewing(false);
    }
  };

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 my-4">
      <div className="flex items-center gap-2 mb-3">
        <FileText className="w-5 h-5 text-amber-600" />
        <h3 className="font-semibold text-amber-800">Employee Draft for Review</h3>
      </div>

      <div className="bg-white rounded p-3 mb-4 text-sm space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <div><span className="text-gray-500">Name:</span> {draft.first_name} {draft.last_name}</div>
          <div><span className="text-gray-500">Email:</span> {draft.email}</div>
          <div><span className="text-gray-500">Designation:</span> {draft.designation}</div>
          <div><span className="text-gray-500">Department:</span> {draft.department}</div>
          <div><span className="text-gray-500">Level:</span> {draft.level}</div>
          <div><span className="text-gray-500">Location:</span> {draft.work_location}</div>
          <div><span className="text-gray-500">Type:</span> {draft.employment_type}</div>
          <div><span className="text-gray-500">Joining:</span> {draft.date_of_joining}</div>
        </div>
        {draft.ctc_annual && (
          <div><span className="text-gray-500">CTC:</span> ₹{(draft.ctc_annual / 100000).toFixed(2)}L per annum</div>
        )}
        {draft.skills && (
          <div><span className="text-gray-500">Skills:</span> {draft.skills}</div>
        )}
      </div>

      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Review Notes (optional for approval, required for rejection)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          rows={2}
          placeholder="Add any notes about this draft..."
        />
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          disabled={reviewing}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          {reviewing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
          Approve
        </button>
        <button
          onClick={handleReject}
          disabled={reviewing}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
        >
          {reviewing ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
          Reject
        </button>
      </div>
    </div>
  );
}
