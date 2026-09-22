# DrKaset Agricultural AI Assistant

A full-stack agricultural AI assistant designed to help Thai farmers access agricultural information through a conversational interface.

The system combines a React frontend, FastAPI backend, MySQL database, FAISS vector search, and Ollama-powered RAG to provide answers based on prepared agricultural reference documents.

## Overview

DrKaset is a web-based agricultural assistant that allows users to ask questions and access agricultural information through a conversational interface.

The system integrates user authentication, chat history, agricultural document retrieval, weather information, and market price information into a single application.

## Features

- User registration, login, JWT refresh, and protected chat history
- AI-powered agricultural question answering
- RAG-based information retrieval from agricultural documents
- Streaming chat responses
- Chat session and message history stored in MySQL
- Weather information
- Agricultural market price information
- Backend health check
- Data preparation pipeline for cleaning, chunking, embedding, and indexing agricultural documents

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, Axios, React Router, React Markdown |
| Backend | FastAPI, Python, SQLAlchemy, Pydantic |
| AI / RAG | Ollama, LangChain, Sentence Transformers, FAISS |
| Database | MySQL |
| Authentication | JWT, bcrypt |

## My Contribution

### Web Application Development

Worked as part of the development team with a focus on the web application.

- Developed and worked with the React-based frontend
- Worked with JavaScript and frontend application development
- Integrated frontend functionality with backend APIs
- Worked on the user interface and application flow
- Participated in testing and system integration

## Project Structure

```text
CSI_AI_DrKaset/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── api/
│   ├── auth/
│   ├── db/
│   ├── rag/
│   └── schemas/
├── frontend/
│   └── src/
├── data_preparation/
└── db/
    ├── init.sql
    └── migrations/
