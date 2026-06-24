import React, { useState, useEffect, useRef } from "react";
import {
  FolderPlus,
  Trash2,
  FileText,
  MessageSquare,
  Send,
  UploadCloud,
  ArrowLeft,
  LogOut,
  Globe,
  AlertCircle,
  Clock,
  Sparkles,
  Info,
  Calendar,
  FileBadge,
  ChevronRight,
  ShieldCheck,
  Search,
  CheckSquare,
  Square,
  User
} from "lucide-react";

import { env } from "./lib/env";

const API_URL = env.API_URL;


// --- Types ---
interface User {
  id: string;
  email: string;
  full_name: string | null;
}

interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

interface DocumentMetadata {
  organization_name: string | null;
  tender_number: string | null;
  submission_deadline: string | null;
  budget_amount: number | null;
  budget_currency: string | null;
  certifications: string[] | null;
  language: string | null;
}

interface Document {
  id: string;
  filename: string;
  status: "uploading" | "processing" | "ready" | "failed";
  doc_type: "tender" | "contract" | "rfp" | "procurement" | "unknown";
  page_count: number | null;
  file_size_bytes: number;
  processing_error: string | null;
  created_at: string;
  metadata?: DocumentMetadata | null;
}

interface ChatSession {
  id: string;
  title: string | null;
  created_at: string;
}

interface SourceInfo {
  page: number;
  snippet: string;
  chunk_id: string | null;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceInfo[] | null;
  isGrounded?: boolean;
}

// --- Lightweight Markdown Parser ---
const renderMarkdown = (text: string) => {
  if (!text) return null;
  
  // Split content by code blocks if any
  const parts = text.split(/(```[\s\S]*?```)/g);
  
  return parts.map((part, index) => {
    // If it's a code block
    if (part.startsWith("```") && part.endsWith("```")) {
      const code = part.slice(3, -3).trim();
      // Remove language tag if present (e.g. @import or javascript)
      const lines = code.split("\n");
      const firstLine = lines[0];
      const hasLang = /^[a-zA-Z0-9_-]+$/.test(firstLine);
      const codeText = hasLang ? lines.slice(1).join("\n") : code;
      
      return (
        <pre key={index} className="bg-black/60 p-4 rounded-lg my-3 border border-[#1e293b] font-mono text-xs overflow-x-auto">
          <code>{codeText}</code>
        </pre>
      );
    }
    
    // Otherwise, process normal text block line-by-line
    const lines = part.split("\n");
    return (
      <div key={index} className="space-y-1.5">
        {lines.map((line, lineIdx) => {
          const trimmed = line.trim();
          if (!trimmed) return <div key={lineIdx} className="h-2" />;
          
          // Header 3
          if (trimmed.startsWith("### ")) {
            return <h4 key={lineIdx} className="text-sm font-bold text-slate-100 mt-3 mb-1">{formatInline(trimmed.slice(4))}</h4>;
          }
          // Header 2
          if (trimmed.startsWith("## ")) {
            return <h3 key={lineIdx} className="text-base font-bold text-slate-400 mt-4 mb-2">{formatInline(trimmed.slice(3))}</h3>;
          }
          // Header 1
          if (trimmed.startsWith("# ")) {
            return <h2 key={lineIdx} className="text-lg font-bold text-slate-100 mt-5 mb-3">{formatInline(trimmed.slice(2))}</h2>;
          }
          
          // Unordered list item
          if (trimmed.startsWith("* ") || trimmed.startsWith("- ")) {
            return (
              <ul key={lineIdx} className="list-disc pl-5 my-1 text-slate-300">
                <li>{formatInline(trimmed.slice(2))}</li>
              </ul>
            );
          }
          
          // Numbered list item
          const matchNum = trimmed.match(/^(\d+)\.\s(.*)/);
          if (matchNum) {
            return (
              <ol key={lineIdx} className="list-decimal pl-5 my-1 text-slate-300">
                <li value={parseInt(matchNum[1], 10)}>{formatInline(matchNum[2])}</li>
              </ol>
            );
          }
          
          // Regular paragraph
          return <p key={lineIdx} className="text-slate-300 leading-relaxed">{formatInline(line)}</p>;
        })}
      </div>
    );
  });
};

const formatInline = (text: string) => {
  // Split by bold markers first **text**
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      const boldText = part.slice(2, -2);
      // Check for inline code inside bold
      return <strong key={i} className="font-bold text-slate-100">{formatInlineCode(boldText)}</strong>;
    }
    return formatInlineCode(part);
  });
};

const formatInlineCode = (text: string) => {
  // Split by inline code markers `text`
  const parts = text.split(/(`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="bg-black/40 px-1.5 py-0.5 rounded font-mono text-xs text-blue-400 border border-[#1e293b]/50">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
};

export default function App() {
  // --- Auth State ---
  const [token, setToken] = useState<string | null>(localStorage.getItem("token"));
  const [user, setUser] = useState<User | null>(null);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authName, setAuthName] = useState("");
  const [isRegistering, setIsRegistering] = useState(false);
  const [authError, setAuthError] = useState("");

  // --- App View State ---
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [activeTab, setActiveTab] = useState<"documents" | "chats">("documents");
  const [isRtl, setIsRtl] = useState(false);

  // --- Modal / Form State ---
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [isCreatingProject, setIsCreatingProject] = useState(false);

  // --- Document State ---
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [selectedDocIdsForChat, setSelectedDocIdsForChat] = useState<string[]>([]);

  // --- Risk Report State ---
  const [activeRiskReport, setActiveRiskReport] = useState<any | null>(null);
  const [isAnalyzingRisks, setIsAnalyzingRisks] = useState(false);

  // --- Proposal State ---
  const [activeProposalDraft, setActiveProposalDraft] = useState<any | null>(null);
  const [isGeneratingProposal, setIsGeneratingProposal] = useState(false);
  const [proposalSubTab, setProposalSubTab] = useState<"summary" | "scope" | "compliance" | "deliverables">("summary");


  // --- Chat State ---
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeSnippet, setActiveSnippet] = useState<SourceInfo | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- Effects ---
  useEffect(() => {
    if (token) {
      fetchCurrentUser();
      fetchProjects();
    } else {
      setUser(null);
      setProjects([]);
    }
  }, [token]);

  useEffect(() => {
    if (activeProject) {
      fetchDocuments();
      fetchChatSessions();
      setSelectedDoc(null);
      setActiveSession(null);
      setMessages([]);
      setSelectedDocIdsForChat([]);
    }
  }, [activeProject]);

  useEffect(() => {
    if (activeSession && activeProject) {
      fetchMessages(activeSession.id);
    }
  }, [activeSession]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // --- Authentication Handlers ---
  const fetchCurrentUser = async () => {
    try {
      const res = await fetch(`${API_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
      } else {
        handleLogout();
      }
    } catch {
      handleLogout();
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      const res = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail, password: authPassword })
      });
      const data = await res.json();
      if (res.ok) {
        localStorage.setItem("token", data.access_token);
        setToken(data.access_token);
      } else {
        setAuthError(data.detail || "Invalid email or password");
      }
    } catch {
      setAuthError("Failed to connect to backend server.");
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      const res = await fetch(`${API_URL}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail, password: authPassword, full_name: authName })
      });
      const data = await res.json();
      if (res.ok) {
        setIsRegistering(false);
        // Automatically login
        const loginRes = await fetch(`${API_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: authEmail, password: authPassword })
        });
        const loginData = await loginRes.json();
        if (loginRes.ok) {
          localStorage.setItem("token", loginData.access_token);
          setToken(loginData.access_token);
        }
      } else {
        setAuthError(data.detail || "Registration failed. Try again.");
      }
    } catch {
      setAuthError("Failed to connect to backend server.");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    setActiveProject(null);
  };

  // --- Project Handlers ---
  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API_URL}/api/projects`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setProjects(data.projects);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    try {
      const res = await fetch(`${API_URL}/api/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ name: newProjectName, description: newProjectDesc })
      });
      if (res.ok) {
        const data = await res.json();
        setProjects([data, ...projects]);
        setActiveProject(data);
        setIsCreatingProject(false);
        setNewProjectName("");
        setNewProjectDesc("");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteProject = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this project? All documents and chats will be deleted.")) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setProjects(projects.filter((p) => p.id !== id));
        if (activeProject?.id === id) {
          setActiveProject(null);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  // --- Document Handlers ---
  const fetchDocuments = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchDocumentDetails = async (docId: string) => {
    if (!activeProject) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${docId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedDoc(data);
        fetchRiskReport(docId);
        fetchProposalDraft(docId);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchRiskReport = async (docId: string) => {
    if (!activeProject) return;
    setActiveRiskReport(null);
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${docId}/risk-analysis`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveRiskReport(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleAnalyzeRisks = async (docId: string) => {
    if (!activeProject) return;
    setIsAnalyzingRisks(true);
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${docId}/risk-analysis`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveRiskReport(data);
      } else {
        if (res.status === 429) {
          try {
            const errData = await res.json();
            alert(errData.detail || "Rate limit exceeded. Please try again in a minute.");
          } catch {
            alert("Rate limit exceeded. Please try again in a minute.");
          }
        } else {
          alert("Risk analysis failed.");
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsAnalyzingRisks(false);
    }
  };

  const fetchProposalDraft = async (docId: string) => {
    if (!activeProject) return;
    setActiveProposalDraft(null);
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${docId}/proposal`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveProposalDraft(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleGenerateProposal = async (docId: string) => {
    if (!activeProject) return;
    setIsGeneratingProposal(true);
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${docId}/proposal`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setActiveProposalDraft(data);
      } else {
        if (res.status === 429) {
          try {
            const errData = await res.json();
            alert(errData.detail || "Rate limit exceeded. Please try again in a minute.");
          } catch {
            alert("Rate limit exceeded. Please try again in a minute.");
          }
        } else {
          alert("Proposal draft generation failed.");
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsGeneratingProposal(false);
    }
  };

  const handleDeleteDocument = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeProject || !confirm("Are you sure you want to delete this document?")) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${docId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setDocuments(documents.filter((d) => d.id !== docId));
        if (selectedDoc?.id === docId) setSelectedDoc(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!activeProject) return;
    setUploadProgress("Uploading...");
    
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });
      
      if (res.ok) {
        const data = await res.json();
        setDocuments([data, ...documents]);
        setUploadProgress("Processing document...");
        
        // Start polling for processing status
        let attempts = 0;
        const interval = setInterval(async () => {
          attempts++;
          const checkRes = await fetch(`${API_URL}/api/projects/${activeProject.id}/documents/${data.id}`, {
            headers: { Authorization: `Bearer ${token}` }
          });
          if (checkRes.ok) {
            const checkData = await checkRes.json();
            if (checkData.status !== "uploading" && checkData.status !== "processing") {
              clearInterval(interval);
              setUploadProgress(null);
              fetchDocuments();
            }
          }
          if (attempts > 30) {
            clearInterval(interval);
            setUploadProgress(null);
            fetchDocuments();
          }
        }, 3000);
      } else {
        const errData = await res.json();
        setUploadProgress(null);
        alert(errData.detail || "Upload failed");
      }
    } catch (err) {
      console.error(err);
      setUploadProgress(null);
      alert("Failed to upload document.");
    }
  };

  const toggleDocSelectionForChat = (docId: string) => {
    if (selectedDocIdsForChat.includes(docId)) {
      setSelectedDocIdsForChat(selectedDocIdsForChat.filter((id) => id !== docId));
    } else {
      setSelectedDocIdsForChat([...selectedDocIdsForChat, docId]);
    }
  };

  // --- Chat Handlers ---
  const fetchChatSessions = async () => {
    if (!activeProject) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/chats`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setChatSessions(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchMessages = async (sessionId: string) => {
    if (!activeProject) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/chats/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!activeProject || !confirm("Are you sure you want to delete this chat history?")) return;
    try {
      const res = await fetch(`${API_URL}/api/projects/${activeProject.id}/chats/${sessionId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setChatSessions(chatSessions.filter((s) => s.id !== sessionId));
        if (activeSession?.id === sessionId) {
          setActiveSession(null);
          setMessages([]);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleStartNewChat = () => {
    setActiveSession(null);
    setMessages([]);
  };

  const handleSendChatMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeProject || isStreaming) return;

    const userQuery = inputMessage;
    setInputMessage("");
    setIsStreaming(true);

    // If new session, we locally create a temporary placeholder message
    const tempUserMsg: Message = {
      id: Math.random().toString(),
      role: "user",
      content: userQuery
    };
    const tempAssistantMsg: Message = {
      id: Math.random().toString(),
      role: "assistant",
      content: ""
    };
    setMessages((prev) => [...prev, tempUserMsg, tempAssistantMsg]);

    try {
      const response = await fetch(`${API_URL}/api/projects/${activeProject.id}/chats/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          message: userQuery,
          session_id: activeSession?.id || null,
          document_ids: selectedDocIdsForChat.length > 0 ? selectedDocIdsForChat : null
        })
      });

      if (!response.ok) {
        if (response.status === 429) {
          try {
            const errData = await response.json();
            throw new Error(errData.detail || "Rate limit exceeded. Please try again in a minute.");
          } catch {
            throw new Error("Rate limit exceeded. Please try again in a minute.");
          }
        }
        throw new Error("Failed to connect to chat stream");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      let buffer = "";
      let currentAssistantText = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        // Keep the last partial line in the buffer
        buffer = lines.pop() || "";

        let currentEvent = "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;

          if (trimmed.startsWith("event: ")) {
            currentEvent = trimmed.slice(7);
          } else if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.slice(6);
            const parsedData = JSON.parse(dataStr);

            if (currentEvent === "sources") {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                last.sources = parsedData;
                return next;
              });
            } else if (currentEvent === "token") {
              if (parsedData === "[CLEAR]") {
                currentAssistantText = "";
              } else {
                currentAssistantText += parsedData;
              }
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                last.content = currentAssistantText;
                return next;
              });
            } else if (currentEvent === "result") {
              const finalSessionId = parsedData.session_id;
              const isGrounded = parsedData.is_grounded;
              
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                last.id = parsedData.message_id;
                last.content = parsedData.final_response;
                last.isGrounded = isGrounded;
                return next;
              });

              // Refresh chat sessions to update title/list
              if (!activeSession) {
                setActiveSession({
                  id: finalSessionId,
                  title: userQuery.slice(0, 50),
                  created_at: new Date().toISOString()
                });
                fetchChatSessions();
              }
            } else if (currentEvent === "error") {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                last.content = `Error: ${parsedData.message}`;
                return next;
              });
            }
          }
        }
      }
    } catch (err: any) {
      console.error(err);
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        last.content = `Stream failed to load: ${err.message || "Unknown error"}`;
        return next;
      });
    } finally {
      setIsStreaming(false);
    }
  };

  // --- Auth View (Login / Register) ---
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-[#070b13] via-[#0b101c] to-[#120f21]">
        <div className="w-full max-w-md glass-panel p-8 animate-slide-in relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-blue-500 to-purple-500"></div>
          
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-purple-500/10 text-purple-400 mb-3 border border-purple-500/20">
              <Sparkles className="w-6 h-6 animate-pulse-glow" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight">APIP</h1>
            <p className="text-sm text-slate-400 mt-1">Arabic Procurement Intelligence Platform</p>
          </div>

          <form onSubmit={isRegistering ? handleRegister : handleLogin} className="flex flex-col gap-4">
            {isRegistering && (
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-slate-400">Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ahmed Ali"
                  value={authName}
                  onChange={(e) => setAuthName(e.target.value)}
                  className="input-field"
                />
              </div>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-400">Email Address</label>
              <input
                type="email"
                required
                placeholder="you@example.com"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                className="input-field"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-slate-400">Password</label>
              <input
                type="password"
                required
                placeholder="••••••••"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                className="input-field"
              />
            </div>

            {authError && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{authError}</span>
              </div>
            )}

            <button type="submit" className="btn-primary w-full justify-center py-3 mt-2">
              {isRegistering ? "Create Account" : "Sign In"}
            </button>
          </form>

          <div className="mt-6 text-center text-xs text-slate-400">
            {isRegistering ? (
              <span>
                Already have an account?{" "}
                <button onClick={() => { setIsRegistering(false); setAuthError(""); }} className="text-blue-400 font-semibold hover:underline">
                  Sign In
                </button>
              </span>
            ) : (
              <span>
                Don't have an account?{" "}
                <button onClick={() => { setIsRegistering(true); setAuthError(""); }} className="text-blue-400 font-semibold hover:underline">
                  Sign Up
                </button>
              </span>
            )}
          </div>
        </div>
      </div>
    );
  }

  // --- Main Dashboard View ---
  if (!activeProject) {
    return (
      <div className="h-screen flex flex-col bg-[#070b13] overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-[#1e293b] px-8 flex items-center justify-between bg-[#0b101c]/80 backdrop-blur-md flex-shrink-0">
          <div className="flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-blue-500" />
            <h1 className="text-lg font-bold tracking-tight">APIP — Arabic Procurement Intelligence Platform</h1>
          </div>
          <div className="flex items-center gap-4">
            {user && (
              <div className="text-sm text-slate-300">
                Logged in as <span className="font-semibold text-slate-100">{user.full_name || user.email}</span>
              </div>
            )}
            <button onClick={handleLogout} className="btn-secondary py-2 px-3 text-red-400 hover:text-red-300">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Dashboard Grid */}
        <main className="flex-1 p-8 max-w-7xl w-full mx-auto animate-slide-in overflow-y-auto min-h-0">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-2xl font-bold">Your Procurement Projects</h2>
              <p className="text-sm text-slate-400">Create or select a project to analyze tenders, contracts and documents.</p>
            </div>
            <button onClick={() => setIsCreatingProject(true)} className="btn-primary">
              <FolderPlus className="w-4 h-4" />
              New Project
            </button>
          </div>

          {/* Project List */}
          {projects.length === 0 ? (
            <div className="glass-panel p-12 text-center max-w-xl mx-auto mt-12 border-dashed">
              <FolderPlus className="w-12 h-12 text-slate-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-1">No Projects Found</h3>
              <p className="text-sm text-slate-400 mb-6">Create a project to start uploading tender documents and checking risks.</p>
              <button onClick={() => setIsCreatingProject(true)} className="btn-primary">
                Create First Project
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {projects.map((p) => (
                <div
                  key={p.id}
                  onClick={() => setActiveProject(p)}
                  className="info-card cursor-pointer group flex flex-col justify-between h-48 relative overflow-hidden"
                >
                  <div>
                    <h3 className="text-lg font-semibold group-hover:text-blue-400 transition-colors flex items-center justify-between">
                      {p.name}
                      <ChevronRight className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-all transform group-hover:translate-x-1" />
                    </h3>
                    <p className="text-sm text-slate-400 mt-2 line-clamp-3">
                      {p.description || "No description provided."}
                    </p>
                  </div>
                  <div className="flex items-center justify-between border-t border-[#1e293b] pt-4 mt-4">
                    <span className="text-xs text-slate-500">
                      Created on {new Date(p.created_at).toLocaleDateString()}
                    </span>
                    <button
                      onClick={(e) => handleDeleteProject(p.id, e)}
                      className="text-slate-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>

        {/* Create Project Modal */}
        {isCreatingProject && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-6 z-50">
            <div className="glass-panel w-full max-w-md p-8 animate-slide-in relative">
              <h3 className="text-lg font-bold mb-4">Create New Project</h3>
              <form onSubmit={handleCreateProject} className="flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-400">Project Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Healthcare Tenders Q3"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    className="input-field"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-semibold text-slate-400">Description</label>
                  <textarea
                    rows={3}
                    placeholder="Describe the target documents or organization scope..."
                    value={newProjectDesc}
                    onChange={(e) => setNewProjectDesc(e.target.value)}
                    className="input-field resize-none"
                  />
                </div>
                <div className="flex items-center justify-end gap-3 mt-2">
                  <button
                    type="button"
                    onClick={() => setIsCreatingProject(false)}
                    className="btn-secondary"
                  >
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary">
                    Create Project
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    );
  }

  // --- Project Workspace View ---
  return (
    <div className={`h-screen flex bg-[#070b13] overflow-hidden ${isRtl ? "rtl-layout" : ""}`}>
      {/* Sidebar - Sessions & Details */}
      <aside className="w-72 border-r border-[#1e293b] bg-[#0b101c]/80 flex flex-col justify-between flex-shrink-0 h-full">
        <div className="flex flex-col flex-1 min-h-0">
          {/* Back to Projects Header */}
          <div className="h-16 px-6 flex items-center justify-between border-b border-[#1e293b] flex-shrink-0">
            <button
              onClick={() => setActiveProject(null)}
              className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>{isRtl ? "المشاريع" : "Projects"}</span>
            </button>
            
            <button
              onClick={() => setIsRtl(!isRtl)}
              className="p-1.5 rounded bg-[#1e293b] text-slate-300 hover:text-slate-100"
              title="Toggle Layout Language (RTL/LTR)"
            >
              <Globe className="w-4 h-4" />
            </button>
          </div>

          {/* Project Identity */}
          <div className="p-6 border-b border-[#1e293b] flex-shrink-0">
            <h2 className="font-bold text-lg text-slate-100 truncate">{activeProject.name}</h2>
            <p className="text-xs text-slate-400 line-clamp-2 mt-1">{activeProject.description || "No description."}</p>
          </div>

          {/* Sidebar Tab Navigation */}
          <div className="flex border-b border-[#1e293b] p-2 gap-1 flex-shrink-0">
            <button
              onClick={() => setActiveTab("documents")}
              className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "documents"
                  ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {isRtl ? "المستندات" : "Documents"}
            </button>
            <button
              onClick={() => setActiveTab("chats")}
              className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "chats"
                  ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {isRtl ? "المحادثات" : "Chats"}
            </button>
          </div>

          {/* Tab Content */}
          <div className="p-4 overflow-y-auto flex-1 min-h-0">
            {activeTab === "documents" ? (
              <div className="flex flex-col gap-2">
                <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider mb-1 px-1">
                  {isRtl ? "اختر المستندات للدردشة" : "Filter chat by docs"}
                </p>
                {documents.length === 0 ? (
                  <span className="text-xs text-slate-500 px-1">{isRtl ? "لا توجد مستندات بعد" : "No documents yet"}</span>
                ) : (
                  documents.map((d) => (
                    <div
                      key={d.id}
                      onClick={() => fetchDocumentDetails(d.id)}
                      className={`p-3 rounded-lg border text-left cursor-pointer transition-all flex items-center justify-between group ${
                        selectedDoc?.id === d.id
                          ? "bg-blue-500/5 border-blue-500/30"
                          : "bg-[#121824]/50 border-transparent hover:border-slate-800"
                      }`}
                    >
                      <div className="flex items-center gap-3 overflow-hidden">
                        {/* Checkbox to filter chat context */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleDocSelectionForChat(d.id);
                          }}
                          className={`flex-shrink-0 text-slate-400 hover:text-blue-400 ${
                            d.status !== "ready" ? "opacity-30 cursor-not-allowed" : ""
                          }`}
                          disabled={d.status !== "ready"}
                        >
                          {selectedDocIdsForChat.includes(d.id) ? (
                            <CheckSquare className="w-4 h-4 text-blue-400" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                        <div className="overflow-hidden">
                          <span className="text-xs font-medium text-slate-200 block truncate">{d.filename}</span>
                          <span className="text-[10px] text-slate-400 block">
                            {d.status === "ready" ? `${d.page_count} pgs` : d.status}
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDeleteDocument(d.id, e)}
                        className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-all p-1"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <button
                  onClick={handleStartNewChat}
                  className="btn-secondary w-full text-xs justify-center py-2 mb-2"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  {isRtl ? "محادثة جديدة" : "New Chat"}
                </button>
                {chatSessions.length === 0 ? (
                  <span className="text-xs text-slate-500 px-1">{isRtl ? "لا توجد محادثات" : "No chats yet"}</span>
                ) : (
                  chatSessions.map((s) => (
                    <div
                      key={s.id}
                      onClick={() => setActiveSession(s)}
                      className={`p-3 rounded-lg border text-left cursor-pointer transition-all flex items-center justify-between group ${
                        activeSession?.id === s.id
                          ? "bg-blue-500/5 border-blue-500/30"
                          : "bg-[#121824]/50 border-transparent hover:border-slate-800"
                      }`}
                    >
                      <span className="text-xs font-medium text-slate-200 truncate pr-2 flex-1">
                        {s.title || "Untitled Session"}
                      </span>
                      <button
                        onClick={(e) => handleDeleteSession(s.id, e)}
                        className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-all p-1"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
        
        {/* Sidebar Footer User Info */}
        <div className="p-4 border-t border-[#1e293b] flex items-center justify-between text-xs text-slate-400 bg-[#080d17]/40 flex-shrink-0">
          <span className="truncate max-w-[120px]">{user?.full_name || user?.email}</span>
          <button onClick={handleLogout} className="text-slate-400 hover:text-red-400 transition-colors p-1">
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </aside>

      {/* Main Workspace Area */}
      <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Document Ingestion & Details Panel */}
        {activeTab === "documents" ? (
          <div 
            className="flex-1 p-8 overflow-y-auto max-w-6xl w-full mx-auto animate-slide-in"
            style={{ maxHeight: 'calc(100vh - 20px)' }}
          >
            {/* Header section */}
            <div className="mb-8">
              <h2 className="text-xl font-bold">{isRtl ? "إدارة مستندات المشروع" : "Project Documents"}</h2>
              <p className="text-xs text-slate-400 mt-1">
                {isRtl ? "قم برفع ملفات عروض الشراء والاتفاقيات لتحليلها وتصنيفها تلقائياً." : "Upload, classify and analyze procurement PDFs."}
              </p>
            </div>

            {/* Ingestion Dropzone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border border-[#1e293b] hover:border-blue-500/50 bg-[#121824]/40 hover:bg-[#121824]/60 rounded-xl p-8 text-center cursor-pointer transition-all border-dashed mb-8 flex flex-col items-center justify-center gap-3 group relative overflow-hidden"
            >
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".pdf,application/pdf"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileUpload(file);
                }}
              />
              <UploadCloud className="w-10 h-10 text-slate-400 group-hover:text-blue-400 transition-colors" />
              <div>
                <span className="text-sm font-semibold text-slate-200 block">
                  {isRtl ? "اضغط لرفع ملف PDF أو اسحبه إلى هنا" : "Upload tender PDF"}
                </span>
                <span className="text-xs text-slate-400 block mt-1">
                  {isRtl ? "الحد الأقصى للملف: 50 ميجابايت" : "Max size 50MB"}
                </span>
              </div>
              {uploadProgress && (
                <div className="absolute inset-0 bg-[#0a0e17]/85 flex items-center justify-center gap-3">
                  <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-xs font-semibold text-blue-400">{uploadProgress}</span>
                </div>
              )}
            </div>

            {/* Document details split view */}
            {selectedDoc ? (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Main Details column */}
                <div className="lg:col-span-2 flex flex-col gap-6">
                  {/* General details card */}
                  <div className="glass-panel p-6">
                    <div className="flex items-center justify-between mb-4 border-b border-[#1e293b] pb-4">
                      <div className="flex items-center gap-3 overflow-hidden">
                        <FileText className="w-8 h-8 text-blue-400 flex-shrink-0" />
                        <div className="overflow-hidden">
                          <h3 className="font-bold text-slate-100 truncate">{selectedDoc.filename}</h3>
                          <span className="text-xs text-slate-400 block uppercase tracking-wider font-semibold">
                            {selectedDoc.doc_type}
                          </span>
                        </div>
                      </div>
                      <span className={`badge badge-${selectedDoc.status}`}>
                        {selectedDoc.status}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-xs">
                      <div>
                        <span className="text-slate-400 block">{isRtl ? "حجم الملف" : "File Size"}</span>
                        <span className="font-semibold text-slate-200 mt-0.5 block">
                          {(selectedDoc.file_size_bytes / 1024 / 1024).toFixed(2)} MB
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block">{isRtl ? "عدد الصفحات" : "Page Count"}</span>
                        <span className="font-semibold text-slate-200 mt-0.5 block">
                          {selectedDoc.page_count || "N/A"}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-400 block">{isRtl ? "تاريخ الرفع" : "Uploaded At"}</span>
                        <span className="font-semibold text-slate-200 mt-0.5 block">
                          {new Date(selectedDoc.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>

                    {selectedDoc.processing_error && (
                      <div className="mt-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                        <h4 className="font-bold mb-1">{isRtl ? "خطأ في المعالجة" : "Processing Error"}</h4>
                        <p>{selectedDoc.processing_error}</p>
                      </div>
                    )}
                  </div>

                  {/* Risk analysis report card */}
                  {selectedDoc.status === "ready" && (
                    <div className="glass-panel p-6">
                      <div className="flex items-center justify-between mb-4 border-b border-[#1e293b] pb-4">
                        <h3 className="font-bold text-slate-100 flex items-center gap-2">
                          <ShieldCheck className="w-5 h-5 text-red-400" />
                          {isRtl ? "تقرير تحليل المخاطر" : "Risk Analysis Report"}
                        </h3>
                        {activeRiskReport && (
                          <span className={`badge ${
                            activeRiskReport.overall_score === 'high' 
                              ? 'bg-red-500/10 text-red-400 border border-red-500/20' 
                              : activeRiskReport.overall_score === 'medium'
                              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          } text-xs font-bold uppercase`}>
                            {isRtl ? "مستوى الخطر:" : "Severity:"} {activeRiskReport.overall_score}
                          </span>
                        )}
                      </div>

                      {!activeRiskReport ? (
                        <div className="text-center p-6">
                          <p className="text-xs text-slate-400 mb-4">
                            {isRtl 
                              ? "لم يتم إجراء تحليل للمخاطر على هذا المستند بعد. قم بتشغيل وكيل تحليل المخاطر لاستخراج وتصنيف البنود الخطرة." 
                              : "Identify critical qualifications, deadlines, legal obligations, and missing annexes."}
                          </p>
                          <button
                            onClick={() => handleAnalyzeRisks(selectedDoc.id)}
                            className="btn-primary text-xs"
                            disabled={isAnalyzingRisks}
                          >
                            {isAnalyzingRisks ? (
                              <>
                                <div className="w-3.5 h-3.5 border border-white border-t-transparent rounded-full animate-spin"></div>
                                <span>{isRtl ? "جاري التحليل..." : "Analyzing..."}</span>
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-3.5 h-3.5" />
                                <span>{isRtl ? "إجراء تحليل المخاطر" : "Run Risk Agent"}</span>
                              </>
                            )}
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {activeRiskReport.risks && activeRiskReport.risks.length === 0 ? (
                            <p className="text-xs text-slate-400 text-center py-4">{isRtl ? "لم يتم العثور على مخاطر واضحة." : "No risks identified."}</p>
                          ) : (
                            <div className="grid grid-cols-1 gap-3 max-h-96 overflow-y-auto pr-1">
                              {activeRiskReport.risks.map((risk: any, i: number) => (
                                <div key={i} className="p-3 bg-[#0a0e17]/40 border border-[#1e293b] rounded-lg text-xs">
                                  <div className="flex items-center justify-between mb-1.5">
                                    <span className="font-semibold text-slate-200">{risk.category}</span>
                                    <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                                      risk.severity === 'high'
                                        ? 'bg-red-500/10 text-red-400'
                                        : risk.severity === 'medium'
                                        ? 'bg-amber-500/10 text-amber-400'
                                        : 'bg-emerald-500/10 text-emerald-400'
                                    }`}>
                                      {risk.severity}
                                    </span>
                                  </div>
                                  <p className="text-slate-300 leading-relaxed mb-2">{risk.description}</p>
                                  {risk.evidence && (
                                    <div className="p-2 bg-[#121824]/85 border border-[#1e293b]/70 rounded text-slate-400 italic flex items-start gap-1">
                                      <span className="text-slate-500">“</span>
                                      <p className="flex-1 text-[11px] leading-normal">{risk.evidence}</p>
                                      {risk.page && (
                                        <button
                                          onClick={() => setActiveSnippet({ page: risk.page, snippet: risk.evidence, chunk_id: null })}
                                          className="text-[10px] text-blue-400 hover:underline flex-shrink-0 ml-1.5"
                                        >
                                          {isRtl ? "صفحة" : "Page"} {risk.page}
                                        </button>
                                      )}
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Proposal draft card */}
                  {selectedDoc.status === "ready" && (
                    <div className="glass-panel p-6">
                      <div className="flex items-center justify-between mb-4 border-b border-[#1e293b] pb-4">
                        <h3 className="font-bold text-slate-100 flex items-center gap-2">
                          <Sparkles className="w-5 h-5 text-purple-400" />
                          {isRtl ? "مسودة مقترح الأعمال" : "Business Proposal Draft"}
                        </h3>
                      </div>

                      {!activeProposalDraft ? (
                        <div className="text-center p-6">
                          <p className="text-xs text-slate-400 mb-4">
                            {isRtl 
                              ? "لم يتم إنشاء مسودة مقترح الأعمال لهذا المستند بعد. قم بتشغيل وكيل كتابة المقترحات لإنشاء ملخص تنفيذي، وفهم النطاق، وقسم الامتثال، والمخرجات المطلوبة." 
                              : "Generate a custom executive summary, scope understanding, compliance section, and deliverables."}
                          </p>
                          <button
                            onClick={() => handleGenerateProposal(selectedDoc.id)}
                            className="btn-primary text-xs"
                            disabled={isGeneratingProposal}
                          >
                            {isGeneratingProposal ? (
                              <>
                                <div className="w-3.5 h-3.5 border border-white border-t-transparent rounded-full animate-spin"></div>
                                <span>{isRtl ? "جاري الإنشاء..." : "Generating..."}</span>
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-3.5 h-3.5" />
                                <span>{isRtl ? "كتابة مسودة مقترح" : "Run Proposal Agent"}</span>
                              </>
                            )}
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {/* Sub-tab navigation for Proposal sections */}
                          <div className="flex border-b border-[#1e293b] p-1 gap-1 bg-[#0b101c]/40 rounded-lg">
                            <button
                              onClick={() => setProposalSubTab("summary")}
                              className={`flex-1 py-1.5 px-2 rounded-md text-[11px] font-semibold transition-all ${
                                proposalSubTab === "summary"
                                  ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              {isRtl ? "الملخص التنفيذي" : "Summary"}
                            </button>
                            <button
                              onClick={() => setProposalSubTab("scope")}
                              className={`flex-1 py-1.5 px-2 rounded-md text-[11px] font-semibold transition-all ${
                                proposalSubTab === "scope"
                                  ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              {isRtl ? "نطاق العمل" : "Scope"}
                            </button>
                            <button
                              onClick={() => setProposalSubTab("compliance")}
                              className={`flex-1 py-1.5 px-2 rounded-md text-[11px] font-semibold transition-all ${
                                proposalSubTab === "compliance"
                                  ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              {isRtl ? "الامتثال" : "Compliance"}
                            </button>
                            <button
                              onClick={() => setProposalSubTab("deliverables")}
                              className={`flex-1 py-1.5 px-2 rounded-md text-[11px] font-semibold transition-all ${
                                proposalSubTab === "deliverables"
                                  ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                                  : "text-slate-400 hover:text-slate-200"
                              }`}
                            >
                              {isRtl ? "المخرجات" : "Deliverables"}
                            </button>
                          </div>

                          <div className="p-4 bg-[#0a0e17]/40 border border-[#1e293b] rounded-lg text-xs leading-relaxed text-slate-300 min-h-48">
                            {proposalSubTab === "summary" && renderMarkdown(activeProposalDraft.executive_summary || "")}
                            {proposalSubTab === "scope" && renderMarkdown(activeProposalDraft.scope_understanding || "")}
                            {proposalSubTab === "compliance" && renderMarkdown(activeProposalDraft.compliance_section || "")}
                            {proposalSubTab === "deliverables" && renderMarkdown(activeProposalDraft.required_deliverables || "")}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Metadata column */}
                <div className="lg:col-span-1">
                  <div className="glass-panel p-6 h-full">
                    <h3 className="font-bold text-slate-200 mb-4 flex items-center gap-2">
                      <FileBadge className="w-4 h-4 text-purple-400" />
                      {isRtl ? "البيانات المستخرجة" : "Extracted Intelligence"}
                    </h3>

                    {!selectedDoc.metadata ? (
                      <div className="text-center p-8 text-xs text-slate-400 border border-dashed border-[#1e293b] rounded-lg">
                        <Clock className="w-8 h-8 text-slate-500 mx-auto mb-2" />
                        {isRtl ? "جاري معالجة البيانات..." : "Metadata still processing..."}
                      </div>
                    ) : (
                      <div className="flex flex-col gap-4 text-xs">
                        <div className="p-3 bg-[#0a0e17]/50 rounded-lg border border-[#1e293b]">
                          <span className="text-slate-400 block mb-0.5">{isRtl ? "الجهة المنظمة" : "Organization"}</span>
                          <span className="font-semibold text-slate-200 block">
                            {selectedDoc.metadata.organization_name || "Not specified"}
                          </span>
                        </div>

                        <div className="p-3 bg-[#0a0e17]/50 rounded-lg border border-[#1e293b]">
                          <span className="text-slate-400 block mb-0.5">{isRtl ? "رقم العطاء/المناقصة" : "Tender Number"}</span>
                          <span className="font-semibold text-slate-200 block">
                            {selectedDoc.metadata.tender_number || "Not specified"}
                          </span>
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 bg-[#0a0e17]/50 rounded-lg border border-[#1e293b]">
                            <span className="text-slate-400 block mb-0.5">{isRtl ? "الميزانية" : "Budget"}</span>
                            <span className="font-semibold text-slate-200 block">
                              {selectedDoc.metadata.budget_amount 
                                ? `${selectedDoc.metadata.budget_amount.toLocaleString()} ${selectedDoc.metadata.budget_currency || ""}`
                                : "N/A"}
                            </span>
                          </div>
                          <div className="p-3 bg-[#0a0e17]/50 rounded-lg border border-[#1e293b]">
                            <span className="text-slate-400 block mb-0.5">{isRtl ? "اللغة الرئيسية" : "Language"}</span>
                            <span className="font-semibold text-slate-200 block">
                              {selectedDoc.metadata.language || "N/A"}
                            </span>
                          </div>
                        </div>

                        <div className="p-3 bg-[#0a0e17]/50 rounded-lg border border-[#1e293b]">
                          <span className="text-slate-400 block mb-1 flex items-center gap-1">
                            <Calendar className="w-3.5 h-3.5 text-blue-400" />
                            {isRtl ? "آخر موعد للتقديم" : "Submission Deadline"}
                          </span>
                          <span className="font-semibold text-slate-200 block">
                            {selectedDoc.metadata.submission_deadline || "Not specified"}
                          </span>
                        </div>

                        <div>
                          <span className="text-slate-400 block mb-2 font-semibold">
                            {isRtl ? "الشهادات المطلوبة" : "Required Certifications"}
                          </span>
                          {selectedDoc.metadata.certifications && selectedDoc.metadata.certifications.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5">
                              {selectedDoc.metadata.certifications.map((c, i) => (
                                <span key={i} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 text-[10px]">
                                  {c}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-500 block italic">{isRtl ? "لا توجد شهادات مطلوبة" : "None identified"}</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center p-12 text-xs text-slate-400 bg-[#121824]/20 border border-[#1e293b] rounded-lg max-w-xl mx-auto">
                <Info className="w-8 h-8 text-slate-500 mx-auto mb-2" />
                {isRtl ? "اختر مستنداً من القائمة الجانبية لعرض تحليله التفصيلي." : "Select a document from the sidebar to view extracted intelligence."}
              </div>
            )}
          </div>
        ) : (
          /* Chat & QA Panel */
          <div className="flex-1 flex flex-col min-h-0 bg-[#0a0e17]/30">
            {/* Chat Session Title Header */}
            <div className="h-16 px-8 border-b border-[#1e293b] flex items-center justify-between bg-[#0b101c]/40 flex-shrink-0">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-blue-500" />
                <span className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                  {activeSession ? (activeSession.title || "Chat Session") : (isRtl ? "محادثة جديدة" : "New Chat")}
                </span>
              </div>
              {selectedDocIdsForChat.length > 0 && (
                <div className="text-xs text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-1 rounded-md">
                  {isRtl ? "مصفى حسب:" : "Filtered context:"} {selectedDocIdsForChat.length} {isRtl ? "مستندات" : "docs"}
                </div>
              )}
            </div>

            {/* Chat History Messages Scroll */}
            <div 
              className="flex-1 overflow-y-auto p-8 space-y-6"
              style={{ maxHeight: 'calc(100vh - 160px)' }}
            >
              {messages.length === 0 ? (
                <div className="text-center max-w-md mx-auto pt-20">
                  <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 flex items-center justify-center mx-auto mb-4">
                    <Search className="w-6 h-6 animate-pulse-glow" />
                  </div>
                  <h3 className="text-sm font-semibold text-slate-200 mb-1">
                    {isRtl ? "اطرح أسئلة حول مستندات المناقصة" : "Ask about tender requirements"}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {isRtl 
                      ? "اسأل عن مواعيد التقديم، الميزانية، الشهادات المطلوبة أو معايير التأهيل." 
                      : "Query details like deadlines, eligibility, technical specifications or certifications."}
                  </p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex gap-4 max-w-3xl ${msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"}`}
                  >
                    {/* Role Avatar */}
                    {msg.role === "user" ? (
                      <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        <User className="w-4 h-4" />
                      </div>
                    ) : (
                      <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 bg-purple-500/10 text-purple-400 border border-purple-500/20 shadow-sm shadow-purple-500/5">
                        <Sparkles className="w-4 h-4 animate-pulse-glow" />
                      </div>
                    )}

                    {/* Message Content Bubble */}
                    <div className="flex flex-col gap-2 min-w-0 flex-1">
                      <div className={`rounded-2xl p-4 text-sm leading-relaxed ${
                        msg.role === "user"
                          ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-tr-sm shadow-lg shadow-blue-500/10 ml-auto"
                          : "bg-[#121824]/90 border border-[#1e293b] text-slate-100 rounded-tl-sm shadow-md mr-auto"
                      }`}>
                        <div>{renderMarkdown(msg.content || "...")}</div>
                      </div>

                      {/* Sources and Grounding status (assistant only) */}
                      {msg.role === "assistant" && (
                        <div className="flex flex-wrap items-center gap-2 mt-1 px-1">
                          {/* Grounding check badge */}
                          {msg.isGrounded !== undefined && msg.sources && msg.sources.length > 0 && (
                            <span className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded ${
                              msg.isGrounded 
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                            }`}>
                              <ShieldCheck className="w-3.5 h-3.5" />
                              {msg.isGrounded 
                                ? (isRtl ? "متحقق من الصحة" : "Grounded Check: Verified")
                                : (isRtl ? "تحذير: غير متحقق" : "Warning: Ungrounded")}
                            </span>
                          )}

                          {/* Sources listing */}
                          {msg.sources && msg.sources.length > 0 && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-[10px] text-slate-500 font-semibold uppercase">{isRtl ? "المصادر:" : "Sources:"}</span>
                              {msg.sources.map((s, i) => (
                                <button
                                  key={i}
                                  onClick={() => setActiveSnippet(s)}
                                  className="text-[10px] bg-[#1e293b] hover:bg-[#2e3b4e] border border-[#2e3b4e] text-slate-300 px-2 py-0.5 rounded cursor-pointer transition-colors"
                                >
                                  {isRtl ? "صفحة" : "Page"} {s.page}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Chat Input form */}
            <div className="p-6 border-t border-[#1e293b] bg-[#0b101c]/30">
              <form onSubmit={handleSendChatMessage} className="flex gap-3 max-w-4xl mx-auto">
                <input
                  type="text"
                  required
                  placeholder={
                    isRtl 
                      ? "اطرح سؤالك هنا حول المستندات المحددة..." 
                      : "Ask a question about the active context..."
                  }
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  className="input-field flex-1 py-3 px-4"
                  disabled={isStreaming}
                />
                <button type="submit" className="btn-primary" disabled={isStreaming}>
                  <Send className="w-4 h-4" />
                </button>
              </form>
            </div>
          </div>
        )}
      </main>

      {/* Snippet Detail Modal */}
      {activeSnippet && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-6 z-50 animate-slide-in">
          <div className="glass-panel w-full max-w-xl p-8 relative flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-[#1e293b] pb-4">
              <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-400" />
                {isRtl ? "مقتطف المصدر" : "Source Snippet"}
              </h3>
              <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 text-xs">
                {isRtl ? "صفحة" : "Page"} {activeSnippet.page}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-300 bg-[#0a0e17]/60 p-4 rounded-lg border border-[#1e293b] whitespace-pre-wrap max-h-96 overflow-y-auto">
              {activeSnippet.snippet}
            </p>
            <div className="flex justify-end">
              <button onClick={() => setActiveSnippet(null)} className="btn-secondary text-xs py-2 px-4">
                {isRtl ? "إغلاق" : "Close"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
