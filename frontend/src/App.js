import React, { useState, useEffect, useRef } from 'react';
import { Search, Send, Mic, Loader2, ChevronRight, Clock, BarChart3, Podcast, Mail, FileText, X } from 'lucide-react';
import axios from 'axios';

const API_BASE = 'http://localhost:3000/api'; // Direct connection to Flask server

// Confidence badge component
const ConfidenceBadge = ({ score }) => {
  const percentage = Math.round(score * 100);
  let colorClass = 'bg-green-500/20 text-green-400 border-green-500/30';
  
  if (percentage < 50) {
    colorClass = 'bg-red-500/20 text-red-400 border-red-500/30';
  } else if (percentage < 75) {
    colorClass = 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
  }
  
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colorClass}`}>
      {percentage}%
    </span>
  );
};

// Search result card component
const SearchResultCard = ({ result, onSelect }) => {
  return (
    <div
      onClick={() => onSelect(result)}
      className="group p-4 rounded-lg bg-zinc-800/50 hover:bg-zinc-800 border border-zinc-700/50 hover:border-zinc-600 transition-all cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h3 className="text-lg font-medium text-white group-hover:text-blue-400 transition-colors">
            {result.title}
          </h3>
          <p className="text-sm text-zinc-400 mt-1">{result.filename}</p>
          <p className="text-sm text-zinc-500 mt-2 line-clamp-2">
            {result.content_preview}
          </p>
        </div>
        <div className="ml-4 flex flex-col items-end space-y-2">
          <ConfidenceBadge score={result.confidence} />
          <ChevronRight className="w-4 h-4 text-zinc-500 group-hover:text-blue-400 transition-colors" />
        </div>
      </div>
      
      {/* Score breakdown on hover */}
      <div className="mt-3 pt-3 border-t border-zinc-700/50 text-xs text-zinc-500 opacity-0 group-hover:opacity-100 transition-opacity">
        <div className="flex space-x-4">
          <span>Title: {(result.scoring.title * 100).toFixed(0)}%</span>
          <span>Intro: {(result.scoring.intro * 100).toFixed(0)}%</span>
          <span>Content: {(result.scoring.content * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
};

// Message component
const Message = ({ message, isUser }) => {
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[70%] ${isUser ? 'order-2' : 'order-1'}`}>
        <div
          className={`rounded-lg px-4 py-3 ${
            isUser
              ? 'bg-blue-600 text-white'
              : 'bg-zinc-800 text-zinc-100 border border-zinc-700'
          }`}
        >
          <p className="text-sm whitespace-pre-wrap">{message}</p>
        </div>
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-zinc-800 rounded-lg border border-zinc-700 p-6 max-w-md w-full">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <Mail className="w-5 h-5 text-blue-500" />
            <h3 className="text-lg font-medium">Email Summary</h3>
          </div>
          <button
            onClick={handleClose}
            className="text-zinc-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <p className="text-sm text-zinc-400 mb-4">
          Get a detailed AI-generated summary of "{podcast?.title}" sent to your email.
        </p>
        
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label htmlFor="email" className="block text-sm font-medium text-zinc-300 mb-2">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              className="w-full px-3 py-2 bg-zinc-900 border border-zinc-600 rounded-md focus:outline-none focus:border-blue-500 transition-colors text-white placeholder-zinc-500"
              disabled={isLoading}
            />
            {emailError && (
              <p className="text-red-400 text-sm mt-1">{emailError}</p>
            )}
          </div>
          
          <div className="flex space-x-3">
            <button
              type="button"
              onClick={handleClose}
              disabled={isLoading}
              className="flex-1 px-4 py-2 text-sm bg-zinc-700 hover:bg-zinc-600 rounded-md transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !email.trim()}
              className="flex-1 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 rounded-md transition-colors disabled:opacity-50 flex items-center justify-center space-x-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Sending...</span>
                </>
              ) : (
                <>
                  <Mail className="w-4 h-4" />
                  <span>Send Summary</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

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
  
  const messagesEndRef = useRef(null);
  const searchInputRef = useRef(null);

  // Fetch stats on mount
  useEffect(() => {
    fetchStats();
  }, []);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus search on mount
  useEffect(() => {
    if (view === 'search') {
      searchInputRef.current?.focus();
    }
  }, [view]);

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API_BASE}/stats`);
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
      setError('Failed to connect to server. Make sure the Flask API is running.');
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    setError(null);
    try {
      const response = await axios.post(`${API_BASE}/search`, {
        query: searchQuery,
        top_k: 5
      });
      
      setSearchResults(response.data.results || []);
      if (response.data.results.length === 0) {
        setError('No podcasts found. Try a different search term.');
      }
    } catch (error) {
      console.error('Search failed:', error);
      setError('Search failed. Please check your connection.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectPodcast = (podcast) => {
    setSelectedPodcast(podcast);
    setView('chat');
    setMessages([]);
    setSessionId(`session_${Date.now()}`);
    setError(null);
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || !selectedPodcast) return;

    const userMessage = inputMessage;
    setInputMessage('');
    setMessages(prev => [...prev, { text: userMessage, isUser: true }]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await axios.post(`${API_BASE}/chat`, {
        podcast_id: selectedPodcast.podcast_id,
        message: userMessage,
        session_id: sessionId
      });
      
      setMessages(prev => [...prev, { text: response.data.response, isUser: false }]);
    } catch (error) {
      console.error('Chat failed:', error);
      setMessages(prev => [...prev, { 
        text: 'Sorry, I encountered an error. Please try again.', 
        isUser: false 
      }]);
    } finally {
      setIsLoading(false);
    }
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

  const handleEmailSummary = async (email) => {
    if (!selectedPodcast) return;
    
    setIsSendingEmail(true);
    setError(null);
    setSuccessMessage('');
    
    try {
      console.log('🔍 Sending summary request:', {
        podcast_id: selectedPodcast.podcast_id,
        email: email,
        podcast_title: selectedPodcast.title
      });

      const response = await axios.post(`${API_BASE}/summary/email`, {
        podcast_id: selectedPodcast.podcast_id,
        email: email
      });
      
      console.log('📧 Summary response:', response.data);
      
      if (response.data.success) {
        setSuccessMessage(`Summary sent successfully to ${email}!`);
        setShowEmailModal(false);
        
        // Clear success message after 5 seconds
        setTimeout(() => setSuccessMessage(''), 5000);
      } else {
        setError(response.data.error || 'Failed to send summary');
      }
    } catch (error) {
      console.error('❌ Summary email failed:', error);
      console.log('📊 Error details:', {
        status: error.response?.status,
        data: error.response?.data,
        message: error.message
      });
      
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

  const handleShowSummary = () => {
    setShowEmailModal(true);
    setError(null);
    setSuccessMessage('');
  };

  return (
    <div className="min-h-screen bg-zinc-900 text-zinc-100">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-900/95 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Podcast className="w-6 h-6 text-blue-500" />
              <h1 className="text-xl font-semibold">Podcast AI</h1>
            </div>
            
            {view === 'chat' && (
              <button
                onClick={handleNewSearch}
                className="text-sm text-zinc-400 hover:text-white transition-colors"
              >
                New Search
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-900/20 border-b border-red-800/50 px-4 py-3">
          <div className="max-w-6xl mx-auto">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        </div>
      )}

      {/* Success Banner */}
      {successMessage && (
        <div className="bg-green-900/20 border-b border-green-800/50 px-4 py-3">
          <div className="max-w-6xl mx-auto">
            <p className="text-sm text-green-400">{successMessage}</p>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {view === 'search' ? (
          <div className="max-w-3xl mx-auto">
            {/* Search Header */}
            <div className="text-center mb-8">
              <h2 className="text-3xl font-light mb-2">
                What podcast would you like to explore?
              </h2>
              <p className="text-zinc-500">
                Search by title, topic, guest name, or describe the content
              </p>
            </div>

            {/* Search Form */}
            <form onSubmit={handleSearch} className="mb-8">
              <div className="relative">
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="e.g., consciousness, joe rogan, AI discussion..."
                  className="w-full px-4 py-3 pl-12 bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:border-blue-500 transition-colors text-white placeholder-zinc-500"
                />
                <Search className="absolute left-4 top-3.5 w-5 h-5 text-zinc-500" />
                {isLoading ? (
                  <Loader2 className="absolute right-4 top-3.5 w-5 h-5 text-zinc-500 animate-spin" />
                ) : (
                  <button
                    type="submit"
                    className="absolute right-2 top-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm font-medium transition-colors"
                  >
                    Search
                  </button>
                )}
              </div>
            </form>

            {/* Stats */}
            {stats && !searchResults.length && (
              <div className="grid grid-cols-3 gap-4 mb-8">
                <div className="bg-zinc-800/50 rounded-lg p-4 text-center">
                  <BarChart3 className="w-5 h-5 text-zinc-500 mx-auto mb-2" />
                  <p className="text-2xl font-light">{stats.database.total_podcasts}</p>
                  <p className="text-sm text-zinc-500">Podcasts</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-4 text-center">
                  <Clock className="w-5 h-5 text-zinc-500 mx-auto mb-2" />
                  <p className="text-2xl font-light">{Math.round(stats.database.total_chunks / 50)}</p>
                  <p className="text-sm text-zinc-500">Hours of content</p>
                </div>
                <div className="bg-zinc-800/50 rounded-lg p-4 text-center">
                  <Search className="w-5 h-5 text-zinc-500 mx-auto mb-2" />
                  <p className="text-2xl font-light">{stats.system.embedding_coverage}%</p>
                  <p className="text-sm text-zinc-500">Indexed</p>
                </div>
              </div>
            )}

            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-zinc-400 mb-3">
                  Found {searchResults.length} podcasts
                </h3>
                {searchResults.map((result, index) => (
                  <SearchResultCard
                    key={index}
                    result={result}
                    onSelect={handleSelectPodcast}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            {/* Chat Header */}
            <div className="bg-zinc-800/50 rounded-lg p-4 mb-6 border border-zinc-700/50">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-lg">{selectedPodcast?.title}</h3>
                  <p className="text-sm text-zinc-500 mt-1">
                    {selectedPodcast?.filename} • Confidence: {Math.round(selectedPodcast?.confidence * 100)}%
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleShowSummary}
                    className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 rounded transition-colors flex items-center space-x-2"
                  >
                    <FileText className="w-4 h-4" />
                    <span>Email Summary</span>
                  </button>
                  <button
                    onClick={handleNewSearch}
                    className="px-3 py-1.5 text-sm bg-zinc-700 hover:bg-zinc-600 rounded transition-colors"
                  >
                    Change Podcast
                  </button>
                </div>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="bg-zinc-800/30 rounded-lg border border-zinc-700/50 p-6 mb-4 min-h-[400px] max-h-[600px] overflow-y-auto">
              {messages.length === 0 && (
                <div className="text-center text-zinc-500 py-8">
                  <Mic className="w-8 h-8 mx-auto mb-3 opacity-50" />
                  <p>Ask me anything about this podcast</p>
                  <p className="text-sm mt-2">I'll answer based on the transcript</p>
                </div>
              )}
              
              {messages.map((message, index) => (
                <Message key={index} message={message.text} isUser={message.isUser} />
              ))}
              
              {isLoading && (
                <div className="flex items-center space-x-2 text-zinc-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Thinking...</span>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>

            {/* Chat Input Form */}
            <form onSubmit={handleSendMessage}>
              <div className="relative">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="Ask about the podcast..."
                  disabled={isLoading}
                  className="w-full px-4 py-3 pr-12 bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:border-blue-500 transition-colors text-white placeholder-zinc-500 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={isLoading || !inputMessage.trim()}
                  className="absolute right-2 top-2 p-1.5 bg-blue-600 hover:bg-blue-700 rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </form>
          </div>
        )}
      </main>

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