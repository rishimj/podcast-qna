import axios from "axios";
const api = axios.create({ baseURL: "http://localhost:3000/api" });

export const searchPodcasts = (query: string, topK = 5) =>
  api.post("/search", { query, top_k: topK });

export const chatWithPodcast = (
  sessionId: string,
  podcastId: number,
  message: string
) =>
  api.post("/chat", {
    session_id: sessionId,
    podcast_id: podcastId,
    message,
  });
