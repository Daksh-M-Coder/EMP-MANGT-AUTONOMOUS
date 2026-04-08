import { useState, useEffect } from 'react';
import { api } from '../lib/api.js';
import { 
  FileText, Check, X, Clock, Filter, RefreshCw,
  ChevronDown, ChevronUp, Loader2, Search
} from 'lucide-react';

export default function Drafts() {
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('pending');
  const [stats, setStats] = useState({ pending: 0, approved: 0, rejected: 0, total: 0 });
  const [expandedDraft, setExpandedDraft] = useState(null);
  const [reviewNotes, setReviewNotes] = useState({});
  const [processing, setProcessing] = useState({});

  useEffect(() => {
    loadDrafts();
    loadStats();
  }, [status]);

  const loadDrafts = async () => {
    setLoading(true);
    try {
      const data = await api.getDrafts(status);
      setDrafts(data.drafts || []);
    } catch (err) {
      console.error('Failed to load drafts:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const data = await api.getDraftStats();
      setStats(data.stats);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const handleApprove = async (draft) => {
    const id = draft.draft_id || draft.id;
    setProcessing(prev => ({ ...prev, [id]: 'approving' }));
    
    try {
      await api.approveDraft(id, reviewNotes[id] || '');
      await loadDrafts();
      await loadStats();
      setExpandedDraft(null);
    } catch (err) {
      alert('Failed to approve: ' + err.message);
    } finally {
      setProcessing(prev => ({ ...prev, [id]: null }));
    }
  };

  const handleReject = async (draft) => {
    const id = draft.draft_id || draft.id;
    const notes = reviewNotes[id];
    
    if (!notes?.trim()) {
      alert('Please provide a reason for rejection');
      return;
    }
    
    setProcessing(prev => ({ ...prev, [id]: 'rejecting' }));
    
    try {
      await api.rejectDraft(id, notes);
      await loadDrafts();
      await loadStats();
      setExpandedDraft(null);
    } catch (err) {
      alert('Failed to reject: ' + err.message);
    } finally {
      setProcessing(prev => ({ ...prev, [id]: null }));
    }
  };

  const getStatusColor = (s) => {
    switch (s) {
      case 'pending': return 'bg-yellow-100 text-yellow-800';
      case 'approved': return 'bg-green-100 text-green-800';
      case 'rejected': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getStatusIcon = (s) => {
    switch (s) {
      case 'pending': return <Clock className="w-4 h-4" />;
      case 'approved': return <Check className="w-4 h-4" />;
      case 'rejected': return <X className="w-4 h-4" />;
      default: return null;
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Employee Drafts</h1>
          <p className="text-gray-500 mt-1">Review and approve AI-generated employee drafts</p>
        </div>
        <button
          onClick={() => { loadDrafts(); loadStats(); }}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white p-4 rounded-lg shadow border">
          <div className="text-2xl font-bold text-yellow-600">{stats.pending}</div>
          <div className="text-sm text-gray-500">Pending Review</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border">
          <div className="text-2xl font-bold text-green-600">{stats.approved}</div>
          <div className="text-sm text-gray-500">Approved</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border">
          <div className="text-2xl font-bold text-red-600">{stats.rejected}</div>
          <div className="text-sm text-gray-500">Rejected</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow border">
          <div className="text-2xl font-bold text-gray-600">{stats.total}</div>
          <div className="text-sm text-gray-500">Total Drafts</div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 mb-4">
        <Filter className="w-4 h-4 text-gray-400" />
        {['pending', 'approved', 'rejected'].map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
              status === s 
                ? 'bg-indigo-600 text-white' 
                : 'bg-white text-gray-600 hover:bg-gray-50 border'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Drafts List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
        </div>
      ) : drafts.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg shadow">
          <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900">No {status} drafts</h3>
          <p className="text-gray-500 mt-1">
            {status === 'pending' 
              ? "New employee drafts created by the AI will appear here for your review."
              : `No ${status} drafts found.`}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {drafts.map((draft) => {
            const id = draft.draft_id || draft.id;
            const isExpanded = expandedDraft === id;
            const data = draft.draft_data || {};
            
            return (
              <div 
                key={id}
                className={`bg-white rounded-lg shadow border overflow-hidden ${
                  isExpanded ? 'ring-2 ring-indigo-500' : ''
                }`}
              >
                {/* Header */}
                <div 
                  className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50"
                  onClick={() => setIsExpanded(isExpanded ? null : id)}
                >
                  <div className="flex items-center gap-4">
                    <div className={`px-2 py-1 rounded-full text-xs font-medium flex items-center gap-1 ${getStatusColor(draft.status)}`}>
                      {getStatusIcon(draft.status)}
                      {draft.status}
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">
                        {data.first_name} {data.last_name}
                      </h3>
                      <p className="text-sm text-gray-500">
                        {data.designation} • {data.department}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right text-sm">
                      <div className="text-gray-500">Proposed by</div>
                      <div className="font-medium">{draft.proposed_by || 'AI System'}</div>
                    </div>
                    <div className="text-right text-sm">
                      <div className="text-gray-500">Date</div>
                      <div className="font-medium">
                        {new Date(draft.proposed_at).toLocaleDateString()}
                      </div>
                    </div>
                    {isExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                  </div>
                </div>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="border-t px-4 py-4">
                    <div className="grid grid-cols-3 gap-4 mb-6">
                      <div>
                        <label className="text-xs text-gray-500 uppercase">Email</label>
                        <div className="font-medium">{data.email}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase">Phone</label>
                        <div className="font-medium">{data.phone || '—'}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase">Level</label>
                        <div className="font-medium">{data.level || '—'}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase">Employment Type</label>
                        <div className="font-medium">{data.employment_type || '—'}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase">Work Location</label>
                        <div className="font-medium">{data.work_location || '—'}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase">Date of Joining</label>
                        <div className="font-medium">{data.date_of_joining || '—'}</div>
                      </div>
                      <div>
                        <label className="text-xs text-gray-500 uppercase">CTC (Annual)</label>
                        <div className="font-medium">
                          {data.ctc_annual ? `₹${(data.ctc_annual / 100000).toFixed(2)}L` : '—'}
                        </div>
                      </div>
                      <div className="col-span-2">
                        <label className="text-xs text-gray-500 uppercase">Skills</label>
                        <div className="font-medium">{data.skills || '—'}</div>
                      </div>
                    </div>

                    {/* Review Notes */}
                    {draft.status === 'pending' && (
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Review Notes
                        </label>
                        <textarea
                          value={reviewNotes[id] || ''}
                          onChange={(e) => setReviewNotes(prev => ({ ...prev, [id]: e.target.value }))}
                          className="w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                          rows={2}
                          placeholder="Add notes about this draft (required for rejection)"
                        />
                      </div>
                    )}

                    {/* Reviewer Info (for approved/rejected) */}
                    {draft.status !== 'pending' && (
                      <div className="bg-gray-50 rounded p-3 mb-4 text-sm">
                        <div className="flex items-center gap-4">
                          <div>
                            <span className="text-gray-500">Reviewed by:</span>
                            <span className="font-medium ml-1">{draft.reviewed_by}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Date:</span>
                            <span className="font-medium ml-1">
                              {new Date(draft.reviewed_at).toLocaleString()}
                            </span>
                          </div>
                          {draft.final_employee_id && (
                            <div>
                              <span className="text-gray-500">Employee ID:</span>
                              <span className="font-medium ml-1">{draft.final_employee_id}</span>
                            </div>
                          )}
                        </div>
                        {draft.review_notes && (
                          <div className="mt-2 text-gray-600">
                            <span className="text-gray-500">Notes:</span> {draft.review_notes}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    {draft.status === 'pending' && (
                      <div className="flex gap-3">
                        <button
                          onClick={() => handleApprove(draft)}
                          disabled={processing[id]}
                          className="flex items-center gap-2 px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                        >
                          {processing[id] === 'approving' ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Check className="w-4 h-4" />
                          )}
                          Approve & Create Employee
                        </button>
                        <button
                          onClick={() => handleReject(draft)}
                          disabled={processing[id]}
                          className="flex items-center gap-2 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                        >
                          {processing[id] === 'rejecting' ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <X className="w-4 h-4" />
                          )}
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
