import React, { useState } from "react";
import { searchPodcasts, chatWithPodcast } from "./api";

interface PodcastResult {
  podcast_id: number;
  title: string;
  filename: string;
  confidence_percent: number;
}

interface Message {
  sender: "system" | "human" | "assistant";
  text: string;
}

export default function App() {
  const [stage, setStage] = useState<"search" | "select" | "chat">("search");
  const [sessionId, setSessionId] = useState<string>("");
  const [podcastId, setPodcastId] = useState<number | null>(null);
  const [results, setResults] = useState<PodcastResult[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const append = (msg: Message) => setMessages((ms) => [...ms, msg]);

  const handleUserInput = async () => {
    const text = input.trim();
    if (!text) return;
    append({ sender: "human", text });
    setInput("");
    setError(null);

    if (stage === "search") {
      append({
        sender: "system",
        text: `Searching for podcasts matching "${text}"...`,
      });
      setLoading(true);
      try {
        const res = await searchPodcasts(text);
        const fetched = res.data.results as PodcastResult[];
        setResults(fetched);
        if (fetched.length === 0) {
          append({
            sender: "system",
            text: `No podcasts found. Try another query.`,
          });
        } else {
          const lines = fetched
            .slice(0, 3)
            .map(
              (r, i) =>
                `${i + 1}. ${r.title} (${r.confidence_percent.toFixed(1)}%)`
            )
            .join("\n");
          append({ sender: "system", text: `Results:\n${lines}` });
          append({
            sender: "system",
            text: "Enter 1–3 to select a podcast, or type a new search.",
          });
          setStage("select");
        }
      } catch (e: any) {
        setError(e.message || "Search failed");
        append({ sender: "system", text: `Error: ${e.message}` });
      } finally {
        setLoading(false);
      }
    } else if (stage === "select") {
      const choice = parseInt(text, 10);
      if (
        !isNaN(choice) &&
        choice >= 1 &&
        choice <= Math.min(3, results.length)
      ) {
        const sel = results[choice - 1];
        setPodcastId(sel.podcast_id);
        setSessionId(`s_${Date.now()}`);
        append({ sender: "system", text: `Selected podcast: ${sel.title}` });
        append({
          sender: "system",
          text: "You can now ask questions about this podcast.",
        });
        setStage("chat");
      } else if (/^search$/i.test(text)) {
        setStage("search");
        append({ sender: "system", text: "Enter a podcast search query." });
      } else {
        setStage("search");
        handleUserInput();
      }
    } else if (stage === "chat") {
      if (!podcastId || !sessionId) return;
      if (/^search$/i.test(text)) {
        setStage("search");
        setResults([]);
        setPodcastId(null);
        append({ sender: "system", text: "Enter a podcast search query." });
        return;
      }
      setLoading(true);
      append({ sender: "system", text: "Thinking..." });
      try {
        const res = await chatWithPodcast(sessionId, podcastId, text);
        append({ sender: "assistant", text: res.data.response });
      } catch (e: any) {
        append({
          sender: "system",
          text: `Error: ${e.message || "Chat failed"}`,
        });
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <h1 className="text-2xl font-semibold text-center">
        Podcast RAG Chatbot
      </h1>
      <div className="p-4 bg-gray-800 rounded h-96 overflow-y-auto space-y-2">
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.sender === "human"
                ? "text-right"
                : m.sender === "assistant"
                ? "text-left"
                : "text-center text-gray-400"
            }
          >
            <pre className="whitespace-pre-wrap inline-block p-1">{m.text}</pre>
          </div>
        ))}
      </div>

      <div className="flex space-x-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleUserInput()}
          className="flex-1 p-2 bg-gray-700 rounded focus:outline-none"
          placeholder={
            stage === "search"
              ? "Type podcast search…"
              : stage === "select"
              ? "Enter 1–3 to select…"
              : 'Ask a question or type "search"'
          }
        />
        <button
          onClick={handleUserInput}
          disabled={loading}
          className="bg-emerald-500 hover:bg-emerald-600 px-4 py-2 rounded disabled:opacity-50"
        >
          Send
        </button>
      </div>

      {loading && <div className="text-center text-gray-500">Loading…</div>}
      {error && <div className="text-red-400 text-center">{error}</div>}
    </div>
  );
}
