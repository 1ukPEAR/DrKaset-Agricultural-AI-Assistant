# DrKaset Agricultural AI Assistant

A full-stack agricultural AI assistant designed to help Thai farmers access agricultural information through a conversational interface.

The system combines a React frontend, FastAPI backend, MySQL database, FAISS vector search, and Ollama-powered RAG to provide answers based on prepared agricultural reference documents.

## Overview

DrKaset is a web-based agricultural assistant developed to support Thai farmers in accessing agricultural information through an AI-powered conversational interface.

The system uses Retrieval-Augmented Generation (RAG) to retrieve relevant information from agricultural documents and provide context-based responses to user questions.

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
| Data Processing | Python, SQL |

## My Contribution

### Data Preparation & RAG

Worked as part of the development team with a focus on data preparation and Retrieval-Augmented Generation (RAG).

- Prepared and structured data for use in the AI system
- Prepared and organized agricultural data for the RAG pipeline
- Built and tested the RAG system using Google Colab
- Experimented with information retrieval to support AI-generated responses

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
