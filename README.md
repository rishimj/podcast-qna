# Podcast Q&A

Search across your podcast library and ask questions about any episode, answered from what was actually said.

![Podcast Q&A search interface](assets/screenshot.png)

## What it does

- **Find the right episode.** Describe a topic, a guest, or a half-remembered idea, and get the most relevant episodes back.
- **Ask questions about it.** Pick an episode and chat with it. Answers come from the transcript, not guesswork.
- **Get a summary.** Generate a summary of any episode, or have it emailed to you.
- **Stays up to date.** New episodes you save on Spotify are picked up and indexed automatically.

## How it works

1. **Collect.** Episodes you save on Spotify are matched to their transcripts.
2. **Index.** Each transcript is split into passages and indexed for both meaning and exact keywords, so searches for concepts and for names both work.
3. **Search.** Your query is matched against every passage, the best matches are re-ranked, and the top episodes are returned.
4. **Answer.** When you ask a question, the most relevant passages from that episode are given to Claude. It writes the answer and checks it against the source before replying.

In testing on 120 queries, the correct episode was the top result 82% of the time and in the top 5 93% of the time.

## Getting started

**Requirements:** Python 3, Node.js, [Ollama](https://ollama.com), and API keys for Pinecone, Anthropic, and Spotify.

```bash
# Install
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# Configure
echo "PINECONE_API_KEY=your-key" > .env
cp config/env/config.env.example config/env/config.env   # add Spotify and Anthropic keys

# Embedding model
ollama pull nomic-embed-text

# Collect and index episodes
python collect_podcasts.py --limit 10
cd backend && python -c "from search.podcast_semantic_search_complete import PodcastTwoTierSearch; PodcastTwoTierSearch().index_all_podcasts_enhanced('../data/transcripts')" && cd ..

# Run
python run_server.py            # API on http://localhost:3000
cd frontend && npm start        # App on http://localhost:8080
```

To keep your library current, `scripts/daily_refresh.sh` collects and indexes new episodes in one step and can run on a schedule.

## Built with

React · FastAPI · Claude · Pinecone · Ollama · SQLite
