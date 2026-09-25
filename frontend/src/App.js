import React, { useState, useEffect, useRef } from 'react';
import {
  Search, Send, Loader2, ArrowLeft, ArrowUpRight, Clock, Layers, Library,
  Headphones, Mail, X, Sparkles, CheckCircle2, AlertCircle,
  BookMarked, ChevronDown, FileText, MessagesSquare, ExternalLink,
} from 'lucide-react';
import axios from 'axios';

// Point REACT_APP_API_BASE at the public API URL when publishing the site.
const API_BASE = `${(process.env.REACT_APP_API_BASE || 'http://localhost:3000').replace(/\/$/, '')}/api`;

// The API may require a shared access code (ACCESS_CODE on the server). It is
// asked for once, kept in localStorage, and sent with every request.
const ACCESS_CODE_KEY = 'podcastQaAccessCode';
const api = axios.create();
api.interceptors.request.use((config) => {
  const code = localStorage.getItem(ACCESS_CODE_KEY);
  if (code) config.headers['X-Access-Code'] = code;
  // Free ngrok tunnels answer browser requests with an interstitial page unless
  // this header is present; it is harmless for any other host.
  config.headers['ngrok-skip-browser-warning'] = '1';
  return config;
});
api.interceptors.response.use(undefined, async (error) => {
  const { response, config } = error;
  if (response?.status === 401 && response.data?.code === 'access_code_required' && !config._retried) {
    const code = window.prompt('This site needs an access code. Enter it to continue:');
    if (code && code.trim()) {
      localStorage.setItem(ACCESS_CODE_KEY, code.trim());
      return api({ ...config, _retried: true });
    }
  }
  return Promise.reject(error);
});

// A user-facing message for a failed request: the server's own explanation
// when it sent one (rate limits, budget, access code), otherwise the fallback.
const describeError = (error, fallback) => {
  const status = error.response?.status;
  const message = error.response?.data?.error;
  if (message && (status === 429 || status === 401 || status === 413 || status === 400)) return message;
  return fallback;
};

const SEARCH_EXAMPLES = ['prompt engineering', 'Elon Musk on DOGE', 'AI and the future of work', 'startup advice'];
const QUESTION_STARTERS = [
  'Summarize the key ideas',
  'Who is the guest and what do they do?',
  'What was the most surprising claim?',
  'Give me three takeaways I can act on',
];

// Transcript previews start with "# Key: value" header lines. Pull out the show,
// the episode name, and the date (filenames begin with YYYY-MM-DD) for display,
// and keep any remaining prose as the excerpt.
const describeEpisode = (result) => {
  const lines = (result?.content_preview || '').split('\n');
  const header = {};
  const body = [];
  lines.forEach((line) => {
    const m = line.match(/^#\s*([^:]+):\s*(.+)$/);
    if (m) header[m[1].trim().toLowerCase()] = m[2].trim();
    else if (!line.startsWith('#') && line.trim()) body.push(line.trim());
  });
  const dateMatch = (result?.filename || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  const date = dateMatch
    ? new Date(Number(dateMatch[1]), Number(dateMatch[2]) - 1, Number(dateMatch[3]))
        .toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    : null;
  return { title: header.episode || result?.title, show: header.show || null, date, excerpt: body.join(' ') };
};

// "Show · Date" line; the show name truncates so the date always stays visible.
const EpisodeMeta = ({ show, date, className = '' }) =>
  show || date ? (
    <p className={`flex min-w-0 gap-1.5 ${className}`}>
      {show && <span className="truncate">{show}</span>}
      {show && date && <span aria-hidden="true">·</span>}
      {date && <span className="shrink-0">{date}</span>}
    </p>
  ) : null;

// Animated equalizer bars, used as the brand mark and as a "listening" indicator.
const Waveform = ({ bars = 5, className = '', animated = true }) => (
  <span className={`inline-flex items-center gap-[3px] ${className}`} aria-hidden="true">
    {Array.from({ length: bars }).map((_, i) => (
      <span
        key={i}
        className={`w-[3px] h-full rounded-full bg-current origin-center ${animated ? 'animate-wave' : ''}`}
        style={{ animationDelay: `${(i * 0.13) % 0.65}s`, transform: animated ? undefined : `scaleY(${[0.5, 0.9, 0.6, 1, 0.45][i % 5]})` }}
      />
    ))}
  </span>
);

// Relevance meter: a thin bar whose colour warms with the match strength.
const RelevanceMeter = ({ score }) => {
  const percentage = Math.round(score * 100);
  const tone = percentage >= 75 ? 'from-amber-300 to-amber-500' : percentage >= 50 ? 'from-amber-500/80 to-orange-600/80' : 'from-ink-500 to-ink-600';
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-16 h-1 rounded-full bg-white/[0.06] overflow-hidden">
        <div className={`h-full rounded-full bg-gradient-to-r ${tone}`} style={{ width: `${percentage}%` }} />
      </div>
      <span className="text-xs tabular-nums text-ink-400">{percentage}%</span>
    </div>
  );
};

// Search result card component
const SearchResultCard = ({ result, index, onSelect }) => {
  const { title, show, date, excerpt } = describeEpisode(result);
  return (
    <button
      type="button"
      onClick={() => onSelect(result)}
      style={{ animationDelay: `${index * 60}ms` }}
      className="group relative w-full text-left p-5 rounded-2xl glass hover:bg-ink-850/80 hover:border-amber-400/20 transition-all duration-300 animate-fade-up focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50"
    >
      <div className="flex items-start gap-4">
        <span className="w-7 shrink-0 font-display text-2xl leading-none text-ink-600 group-hover:text-amber-400/80 transition-colors tabular-nums pt-0.5">
          {String(index + 1).padStart(2, '0')}
        </span>
        <div className="flex-1 min-w-0">
          <EpisodeMeta show={show} date={date} className="text-[11px] uppercase tracking-[0.14em] text-amber-400/70 mb-1.5" />
          <div className="flex items-start justify-between gap-4">
            <h3 className="text-[17px] font-medium text-ink-100 group-hover:text-white transition-colors leading-snug">
              {title}
            </h3>
            <ArrowUpRight className="w-4 h-4 shrink-0 mt-1 text-ink-500 group-hover:text-amber-400 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all" />
          </div>
          {excerpt && (
            <p className="text-sm text-ink-400 mt-2 line-clamp-2 leading-relaxed">{excerpt}</p>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
            <RelevanceMeter score={result.confidence} />
            <div className="flex gap-3 text-[11px] uppercase tracking-wider text-ink-500 opacity-0 group-hover:opacity-100 transition-opacity">
              <span>Title {(result.scoring.title * 100).toFixed(0)}</span>
              <span>Intro {(result.scoring.intro * 100).toFixed(0)}</span>
              <span>Content {(result.scoring.content * 100).toFixed(0)}</span>
            </div>
          </div>
        </div>
      </div>
    </button>
  );
};

// Message component
// Claude answers in Markdown. Render **bold** as <strong> elements (never raw
// HTML); everything else stays text, and whitespace-pre-wrap keeps the line
// breaks and numbered lists readable.
const renderBold = (text) =>
  typeof text !== 'string'
    ? text
    : text.split(/(\*\*[^*\n]+\*\*)/g).map((part, i) =>
        part.length > 4 && part.startsWith('**') && part.endsWith('**')
          ? <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>
          : part
      );

const Message = ({ message, isUser }) => {
  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-up">
        <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl rounded-br-md px-4 py-2.5 bg-amber-400/[0.12] border border-amber-400/20 text-amber-50">
          <p className="text-[15px] whitespace-pre-wrap leading-relaxed">{message}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3 animate-fade-up">
      <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-amber-300 to-orange-500 flex items-center justify-center text-ink-950">
        <Sparkles className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0 pt-1">
        <p className="text-[15px] whitespace-pre-wrap leading-relaxed text-ink-200">{renderBold(message)}</p>
      </div>
    </div>
  );
};

// Email Summary Modal component
const EmailSummaryModal = ({ isOpen, onClose, podcast, onSendEmail, isLoading }) => {
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState('');

  const validateEmail = (email) => {
    const re = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    return re.test(email);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setEmailError('');

    if (!email.trim()) {
      setEmailError('Email is required');
      return;
    }

    if (!validateEmail(email)) {
      setEmailError('Please enter a valid email address');
      return;
    }

    onSendEmail(email);
  };

  const handleClose = () => {
    setEmail('');
    setEmailError('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={handleClose}>
      <div
        className="relative w-full max-w-md rounded-3xl glass bg-ink-900/95 p-7 shadow-2xl shadow-black/50 animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={handleClose}
          className="absolute top-5 right-5 p-1.5 rounded-full text-ink-400 hover:text-white hover:bg-white/[0.06] transition-colors"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="w-11 h-11 rounded-2xl bg-amber-400/10 border border-amber-400/20 flex items-center justify-center mb-5">
          <Mail className="w-5 h-5 text-amber-300" />
        </div>
        <h3 className="font-display text-3xl text-white">Email a summary</h3>
        <p className="text-sm text-ink-400 mt-2 mb-6 leading-relaxed">
          We'll write up a detailed summary of <span className="text-ink-200">{describeEpisode(podcast).title}</span> and send it to your inbox.
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email" className="block text-xs font-medium uppercase tracking-wider text-ink-400 mb-2">
            Email address
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoFocus
            className="w-full px-4 py-3 bg-ink-950/60 border border-white/[0.08] rounded-xl focus:outline-none focus:border-amber-400/50 focus:ring-4 focus:ring-amber-400/10 transition-all text-white placeholder-ink-500"
            disabled={isLoading}
          />
          {emailError && (
            <p className="text-red-400 text-sm mt-2">{emailError}</p>
          )}

          <div className="flex gap-3 mt-6">
            <button
              type="button"
              onClick={handleClose}
              disabled={isLoading}
              className="flex-1 px-4 py-2.5 text-sm rounded-xl btn-ghost"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !email.trim()}
              className="flex-1 px-4 py-2.5 text-sm rounded-xl btn-accent flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Sending…</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Send summary</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// "Save to Notion" button with a menu: the episode summary, or this conversation.
const NotionMenu = ({ onExport, busy, hasConversation }) => {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => {
      if (e.type === 'keydown' ? e.key === 'Escape' : !menuRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  const choose = (kind) => {
    setOpen(false);
    onExport(kind);
  };

  const itemClass = 'w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-white/[0.05] disabled:opacity-40 disabled:hover:bg-transparent transition-colors';

  return (
    <div ref={menuRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={!!busy}
        aria-haspopup="menu"
        aria-expanded={open}
        className="px-4 py-2 text-sm rounded-xl btn-ghost hover:border-amber-400/30 hover:text-amber-100 flex items-center gap-2"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <BookMarked className="w-4 h-4" />}
        <span>{busy ? 'Saving…' : 'Save to Notion'}</span>
        {!busy && <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />}
      </button>
      {open && (
        <div role="menu" className="absolute left-0 sm:left-auto sm:right-0 mt-2 w-64 z-30 p-1.5 rounded-2xl glass bg-ink-900/95 shadow-2xl shadow-black/50 animate-scale-in">
          <button role="menuitem" onClick={() => choose('summary')} className={itemClass}>
            <FileText className="w-4 h-4 mt-0.5 shrink-0 text-amber-300" />
            <span>
              <span className="block text-sm text-ink-100">Episode summary</span>
              <span className="block text-xs text-ink-500 mt-0.5">A detailed write-up of the whole episode</span>
            </span>
          </button>
          <button role="menuitem" onClick={() => choose('conversation')} disabled={!hasConversation} className={itemClass}>
            <MessagesSquare className="w-4 h-4 mt-0.5 shrink-0 text-amber-300" />
            <span>
              <span className="block text-sm text-ink-100">This conversation</span>
              <span className="block text-xs text-ink-500 mt-0.5">
                {hasConversation ? 'Your questions and the answers' : 'Ask a question first'}
              </span>
            </span>
          </button>
        </div>
      )}
    </div>
  );
};

// Floating notice for errors and confirmations.
const Toast = ({ tone, children, onDismiss }) => {
  const isError = tone === 'error';
  const Icon = isError ? AlertCircle : CheckCircle2;
  return (
    <div className="fixed top-20 inset-x-0 z-40 flex justify-center px-4 pointer-events-none">
      <div
        className={`pointer-events-auto flex items-start gap-3 max-w-xl w-full sm:w-auto rounded-2xl px-4 py-3 backdrop-blur-xl border shadow-xl shadow-black/30 animate-fade-up ${
          isError ? 'bg-red-950/80 border-red-500/20 text-red-200' : 'bg-emerald-950/80 border-emerald-500/20 text-emerald-200'
        }`}
        role={isError ? 'alert' : 'status'}
      >
        <Icon className={`w-5 h-5 shrink-0 mt-px ${isError ? 'text-red-400' : 'text-emerald-400'}`} />
        <p className="text-sm leading-relaxed flex-1">{children}</p>
        <button onClick={onDismiss} className="shrink-0 opacity-60 hover:opacity-100 transition-opacity" aria-label="Dismiss">
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

const Stat = ({ icon: Icon, value, label }) => (
  <div className="flex-1 px-4 py-5 text-center">
    <Icon className="w-4 h-4 text-amber-400/70 mx-auto mb-3" />
    <p className="font-display text-4xl text-white tabular-nums">{Number(value).toLocaleString()}</p>
    <p className="text-xs uppercase tracking-wider text-ink-500 mt-1">{label}</p>
  </div>
);

// Main App Component
function App() {
  const [view, setView] = useState('search'); // 'search' or 'chat'
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedPodcast, setSelectedPodcast] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  // Summary functionality
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [isSendingEmail, setIsSendingEmail] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [notionExport, setNotionExport] = useState(null); // 'summary' | 'conversation' while saving

  const messagesEndRef = useRef(null);
  const searchInputRef = useRef(null);
  const chatInputRef = useRef(null);

  // Fetch stats on mount
  useEffect(() => {
    fetchStats();
  }, []);

  // Auto-scroll messages
  useEffect(() => {
    if (messages.length || isLoading) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  // Focus the input for the current view
  useEffect(() => {
    if (view === 'search') {
      searchInputRef.current?.focus();
    } else {
      chatInputRef.current?.focus();
    }
  }, [view]);

  const fetchStats = async () => {
    try {
      const response = await api.get(`${API_BASE}/stats`);
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
      setError('Failed to connect to server. Make sure the API server is running (python run_server.py).');
    }
  };

  const runSearch = async (query) => {
    if (!query.trim()) return;

    setIsLoading(true);
    setError(null);
    try {
      const response = await api.post(`${API_BASE}/search`, {
        query,
        top_k: 5
      });

      setSearchResults(response.data.results || []);
      if (response.data.results.length === 0) {
        setError('No podcasts found. Try a different search term.');
      }
    } catch (error) {
      console.error('Search failed:', error);
      setError(describeError(error, 'Search failed. Please check your connection.'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    runSearch(searchQuery);
  };

  const handleExampleSearch = (example) => {
    setSearchQuery(example);
    runSearch(example);
  };

  const handleSelectPodcast = (podcast) => {
    setSelectedPodcast(podcast);
    setView('chat');
    setMessages([]);
    setSessionId(`session_${Date.now()}`);
    setError(null);
    window.scrollTo({ top: 0 });
  };

  const sendMessage = async (text) => {
    if (!text.trim() || !selectedPodcast || isLoading) return;

    setInputMessage('');
    setMessages(prev => [...prev, { text, isUser: true }]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.post(`${API_BASE}/chat`, {
        podcast_id: selectedPodcast.podcast_id,
        message: text,
        session_id: sessionId
      });

      setMessages(prev => [...prev, { text: response.data.response, isUser: false }]);
    } catch (error) {
      console.error('Chat failed:', error);
      setMessages(prev => [...prev, {
        text: describeError(error, 'Sorry, I encountered an error. Please try again.'),
        isUser: false
      }]);
    } finally {
      setIsLoading(false);
      chatInputRef.current?.focus();
    }
  };

  const handleSendMessage = (e) => {
    e.preventDefault();
    sendMessage(inputMessage);
  };

  const handleNewSearch = () => {
    setView('search');
    setSearchQuery('');
    setSearchResults([]);
    setSelectedPodcast(null);
    setMessages([]);
    setError(null);
    setSuccessMessage('');
  };

  const handleBackToResults = () => {
    setView('search');
    setSelectedPodcast(null);
    setMessages([]);
    setError(null);
  };

  const handleEmailSummary = async (email) => {
    if (!selectedPodcast) return;

    setIsSendingEmail(true);
    setError(null);
    setSuccessMessage('');

    try {
      const response = await api.post(`${API_BASE}/summary/email`, {
        podcast_id: selectedPodcast.podcast_id,
        email: email
      });

      if (response.data.success) {
        setSuccessMessage(`Summary sent successfully to ${email}!`);
        setShowEmailModal(false);

        // Clear success message after 5 seconds
        setTimeout(() => setSuccessMessage(''), 5000);
      } else {
        setError(response.data.error || 'Failed to send summary');
      }
    } catch (error) {
      if (error.response?.data?.error) {
        setError(error.response.data.error);
      } else if (error.response?.status === 404) {
        setError(`Podcast not found. Please try selecting a different podcast.`);
      } else if (error.response?.status >= 500) {
        setError('Server error. Please check that the backend is running and try again.');
      } else {
        setError('Failed to send summary. Please check your connection and try again.');
      }
    } finally {
      setIsSendingEmail(false);
    }
  };

  const handleNotionExport = async (kind) => {
    if (!selectedPodcast || notionExport) return;

    setNotionExport(kind);
    setError(null);
    setSuccessMessage('');

    try {
      const response = kind === 'summary'
        ? await api.post(`${API_BASE}/notion/summary`, { podcast_id: selectedPodcast.podcast_id })
        : await api.post(`${API_BASE}/notion/conversation`, { session_id: sessionId });

      const { notion_url: url } = response.data;
      setSuccessMessage(
        <>
          {kind === 'summary' ? 'Summary' : 'Conversation'} saved to Notion.{' '}
          {url && (
            <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-white">
              Open page <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </>
      );
      setTimeout(() => setSuccessMessage(''), 8000);
    } catch (error) {
      const status = error.response?.status;
      // Notion's own explanation (502) and "not configured" (503) are worth showing as-is.
      const detail = (status === 502 || status === 503 || status === 404) && error.response?.data?.error;
      setError(detail || describeError(error, 'Could not save to Notion. Please try again.'));
    } finally {
      setNotionExport(null);
    }
  };

  const handleShowSummary = () => {
    setShowEmailModal(true);
    setError(null);
    setSuccessMessage('');
  };

  const hasResults = searchResults.length > 0;
  const episode = describeEpisode(selectedPodcast);

  return (
    <div className="relative min-h-screen bg-ink-950 text-ink-100 overflow-x-hidden">
      {/* Ambient background */}
      <div className="pointer-events-none fixed inset-0 backdrop-glow" />
      <div className="pointer-events-none fixed inset-0 grain" />

      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-white/[0.05] bg-ink-950/70 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <button onClick={handleNewSearch} className="flex items-center gap-2.5 group">
            <span className="w-8 h-8 rounded-xl bg-gradient-to-br from-amber-300 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <Waveform bars={4} animated={false} className="h-3.5 text-ink-950" />
            </span>
            <span className="font-display text-2xl text-white tracking-tight">Podcast AI</span>
          </button>

          {view === 'chat' && (
            <button
              onClick={handleNewSearch}
              className="flex items-center gap-2 text-sm px-3.5 py-1.5 rounded-full btn-ghost"
            >
              <Search className="w-3.5 h-3.5" />
              <span>New search</span>
            </button>
          )}
        </div>
      </header>

      {/* Notices */}
      {error && <Toast tone="error" onDismiss={() => setError(null)}>{error}</Toast>}
      {!error && successMessage && <Toast tone="success" onDismiss={() => setSuccessMessage('')}>{successMessage}</Toast>}

      {/* Main Content */}
      <main className="relative max-w-5xl mx-auto px-4 sm:px-6">
        {view === 'search' ? (
          <div className={`max-w-2xl mx-auto transition-all duration-500 ${hasResults ? 'pt-10 pb-16' : 'pt-20 sm:pt-28 pb-16'}`}>
            {/* Search Header */}
            {!hasResults && (
              <div className="text-center mb-10 animate-fade-up">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-amber-400/20 bg-amber-400/[0.06] text-amber-200/90 text-xs mb-6">
                  <Waveform bars={4} className="h-3 text-amber-400" />
                  <span>Ask anything, answered from the transcript</span>
                </div>
                <h2 className="font-display text-5xl sm:text-6xl leading-[1.05] text-white tracking-tight">
                  What do you want to <em className="text-transparent bg-clip-text bg-gradient-to-r from-amber-200 via-amber-400 to-orange-400">explore</em> today?
                </h2>
                <p className="text-ink-400 mt-4 text-lg">
                  Search by title, topic, guest, or just describe the conversation.
                </p>
              </div>
            )}

            {/* Search Form */}
            <form onSubmit={handleSearch} className="relative group">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-amber-400/30 via-orange-500/20 to-amber-400/30 opacity-0 group-focus-within:opacity-100 blur-md transition-opacity duration-500" />
              <div className="relative flex items-center rounded-2xl glass bg-ink-900/80 shadow-2xl shadow-black/40 group-focus-within:border-amber-400/30 transition-colors">
                <Search className="ml-5 w-5 h-5 text-ink-500 shrink-0" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="a topic, a guest's name, that episode about AI agents…"
                  className="flex-1 min-w-0 bg-transparent px-4 py-4 sm:py-5 text-base sm:text-lg text-white placeholder-ink-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={isLoading || !searchQuery.trim()}
                  className="mr-2 px-4 sm:px-5 py-2.5 rounded-xl btn-accent text-sm flex items-center gap-2"
                >
                  {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <span>Search</span>}
                </button>
              </div>
            </form>

            {/* Example searches */}
            {!hasResults && (
              <div className="flex flex-wrap justify-center gap-2 mt-5 animate-fade-up" style={{ animationDelay: '120ms' }}>
                <span className="text-xs text-ink-500 py-1.5">Try</span>
                {SEARCH_EXAMPLES.map((example) => (
                  <button
                    key={example}
                    onClick={() => handleExampleSearch(example)}
                    disabled={isLoading}
                    className="text-xs px-3 py-1.5 rounded-full btn-ghost hover:text-amber-200 hover:border-amber-400/30"
                  >
                    {example}
                  </button>
                ))}
              </div>
            )}

            {/* Stats */}
            {stats && !hasResults && (
              <div className="mt-16 flex divide-x divide-white/[0.06] rounded-2xl glass animate-fade-up" style={{ animationDelay: '200ms' }}>
                <Stat icon={Library} value={stats.database.total_podcasts} label="Episodes" />
                <Stat icon={Clock} value={Math.round(stats.database.total_chunks / 50)} label="Hours" />
                <Stat icon={Layers} value={stats.pinecone?.total_vectors || 0} label="Passages indexed" />
              </div>
            )}

            {/* Search Results */}
            {hasResults && (
              <div className="mt-10">
                <div className="flex items-baseline justify-between mb-4 px-1">
                  <h3 className="font-display text-2xl text-white">
                    {searchResults.length} {searchResults.length === 1 ? 'episode' : 'episodes'} found
                  </h3>
                  <span className="text-xs text-ink-500">Pick one to start asking</span>
                </div>
                <div className="space-y-3">
                  {searchResults.map((result, index) => (
                    <SearchResultCard
                      key={result.podcast_id ?? index}
                      index={index}
                      result={result}
                      onSelect={handleSelectPodcast}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="max-w-3xl mx-auto pt-8 pb-40">
            <button
              onClick={handleBackToResults}
              className="flex items-center gap-1.5 text-sm text-ink-400 hover:text-white transition-colors mb-5"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to results</span>
            </button>

            {/* Episode Header */}
            <div className="relative overflow-hidden rounded-3xl glass p-6 sm:p-7 animate-fade-up">
              <div className="absolute -top-24 -right-16 w-64 h-64 rounded-full bg-amber-500/10 blur-3xl" />
              <div className="relative flex flex-col sm:flex-row sm:items-center gap-5">
                <div className="w-16 h-16 shrink-0 rounded-2xl bg-gradient-to-br from-amber-300 via-amber-500 to-orange-600 flex items-center justify-center shadow-xl shadow-amber-600/20">
                  <Headphones className="w-7 h-7 text-ink-950" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] uppercase tracking-[0.18em] text-amber-400/80 mb-1.5">Now exploring</p>
                  <h3 className="font-display text-3xl leading-tight text-white">{episode.title}</h3>
                  <EpisodeMeta show={episode.show} date={episode.date} className="text-sm text-ink-500 mt-1.5" />
                </div>
                <div className="shrink-0 self-start sm:self-center flex flex-wrap gap-2">
                  {/* Hidden when the server has emailing turned off (EMAIL_ENABLED=0). */}
                  {stats?.features?.email_summary !== false && (
                    <button
                      onClick={handleShowSummary}
                      className="px-4 py-2 text-sm rounded-xl btn-ghost hover:border-amber-400/30 hover:text-amber-100 flex items-center gap-2"
                    >
                      <Mail className="w-4 h-4" />
                      <span>Email summary</span>
                    </button>
                  )}
                  {/* Shown only when the server has Notion set up (NOTION_TOKEN) and enabled. */}
                  {stats?.features?.notion_export && (
                    <NotionMenu
                      onExport={handleNotionExport}
                      busy={notionExport}
                      hasConversation={messages.some((m) => !m.isUser) && !isLoading}
                    />
                  )}
                </div>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="mt-8 space-y-6">
              {messages.length === 0 && (
                <div className="text-center py-10 animate-fade-up" style={{ animationDelay: '100ms' }}>
                  <Waveform bars={7} className="h-8 text-amber-400/60" />
                  <p className="font-display text-3xl text-white mt-5">Ask me anything about this episode</p>
                  <p className="text-sm text-ink-500 mt-2">Answers are grounded in the transcript.</p>
                  <div className="grid sm:grid-cols-2 gap-2.5 mt-8 text-left">
                    {QUESTION_STARTERS.map((q) => (
                      <button
                        key={q}
                        onClick={() => sendMessage(q)}
                        className="group flex items-center justify-between gap-3 px-4 py-3 rounded-xl glass hover:border-amber-400/25 hover:bg-ink-850/80 transition-all text-sm text-ink-300 hover:text-white"
                      >
                        <span>{q}</span>
                        <ArrowUpRight className="w-4 h-4 shrink-0 text-ink-600 group-hover:text-amber-400 transition-colors" />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message, index) => (
                <Message key={index} message={message.text} isUser={message.isUser} />
              ))}

              {isLoading && (
                <div className="flex gap-3 items-center animate-fade-up">
                  <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-amber-300 to-orange-500 flex items-center justify-center text-ink-950">
                    <Sparkles className="w-4 h-4" />
                  </div>
                  <div className="flex items-center gap-2.5 text-sm text-ink-400">
                    <Waveform bars={5} className="h-4 text-amber-400" />
                    <span>Listening back through the episode…</span>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        )}
      </main>

      {/* Chat composer, pinned to the bottom of the viewport */}
      {view === 'chat' && (
        <div className="fixed bottom-0 inset-x-0 z-20 bg-gradient-to-t from-ink-950 via-ink-950/95 to-transparent pt-10 pb-5 sm:pb-7">
          <form onSubmit={handleSendMessage} className="max-w-3xl mx-auto px-4 sm:px-6">
            <div className="relative group">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-amber-400/25 via-orange-500/15 to-amber-400/25 opacity-0 group-focus-within:opacity-100 blur-md transition-opacity duration-500" />
              <div className="relative flex items-center rounded-2xl glass bg-ink-900/90 shadow-2xl shadow-black/50 group-focus-within:border-amber-400/30 transition-colors">
                <input
                  ref={chatInputRef}
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="Ask about this episode…"
                  disabled={isLoading}
                  className="flex-1 min-w-0 bg-transparent pl-5 pr-3 py-4 text-[15px] text-white placeholder-ink-500 focus:outline-none disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={isLoading || !inputMessage.trim()}
                  className="mr-2 w-10 h-10 rounded-xl btn-accent flex items-center justify-center"
                  aria-label="Send"
                >
                  {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Email Summary Modal */}
      <EmailSummaryModal
        isOpen={showEmailModal}
        onClose={() => setShowEmailModal(false)}
        podcast={selectedPodcast}
        onSendEmail={handleEmailSummary}
        isLoading={isSendingEmail}
      />
    </div>
  );
}

export default App;
