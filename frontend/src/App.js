import React, { useState, useEffect, useRef } from 'react';
import { Search, Send, Mic, Loader2, ChevronRight, Clock, BarChart3, Podcast } from 'lucide-react';
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
                <button
                  onClick={handleNewSearch}
                  className="px-3 py-1.5 text-sm bg-zinc-700 hover:bg-zinc-600 rounded transition-colors"
                >
                  Change Podcast
                </button>
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
    </div>
  );
}

export default App;