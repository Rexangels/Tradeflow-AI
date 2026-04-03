import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
  BarChart, Bar
} from 'recharts';
import { 
  TrendingUp, TrendingDown, Activity, Settings, Play, Database, 
  BarChart3, LayoutDashboard, History, Zap, Shield, Info,
  ChevronRight, Search, Filter, Download, Share2, Plus, Trash2,
  MessageSquare, Send, X, Pause, RotateCcw, Brain
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from './lib/utils';
import { Candle, Timeframe, DataSource, AgentConfig, Strategy, BacktestResult, Trade } from './types';
import { CandlestickChart } from './components/CandlestickChart';

// Mock Data Generator
const generateMockData = (days: number = 100): Candle[] => {
  const data: Candle[] = [];
  let price = 100;
  const now = new Date();
  for (let i = 0; i < days; i++) {
    const time = new Date(now.getTime() - (days - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
    const change = (Math.random() - 0.48) * 5;
    const open = price;
    const close = price + change;
    const high = Math.max(open, close) + Math.random() * 2;
    const low = Math.min(open, close) - Math.random() * 2;
    data.push({ time, open, high, low, close, volume: Math.random() * 1000000 });
    price = close;
  }
  return data;
};

import { fetchBinanceData } from './services/marketData';
import { runBacktest as executeBacktest } from './services/backtest';

import { AuthProvider, useAuth } from './contexts/AuthContext';
import { db, handleFirestoreError, OperationType } from './firebase';
import { collection, addDoc, query, where, onSnapshot, orderBy, limit, setDoc, doc } from 'firebase/firestore';

import { sendMessage, handleToolCall, chat, generateAIReflection } from './services/geminiService';

function AppContent() {
  const { user, loading, signIn, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<'dashboard' | 'backtest' | 'agents' | 'data' | 'live'>('dashboard');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [timeframe, setTimeframe] = useState<Timeframe>('1h');
  const [source, setSource] = useState<DataSource>('Binance');
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [marketData, setMarketData] = useState<Candle[]>([]);
  const [savedBacktests, setSavedBacktests] = useState<any[]>([]);
  const [savedAgents, setSavedAgents] = useState<AgentConfig[]>([]);
  const [isSavingAgent, setIsSavingAgent] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  // AI Chat State
  const [chatMessages, setChatMessages] = useState<{ role: 'user' | 'ai', content: string }[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [showCommandCenter, setShowCommandCenter] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Backtest Playback State
  const [playbackIndex, setPlaybackIndex] = useState<number | undefined>(undefined);
  const [isPlaybackRunning, setIsPlaybackRunning] = useState(false);
  const playbackTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!user) return;

    const q = query(
      collection(db, 'chats'),
      where('userId', '==', user.uid),
      orderBy('createdAt', 'asc')
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const messages = snapshot.docs.map(doc => ({
        role: doc.data().role as 'user' | 'ai',
        content: doc.data().content
      }));
      if (messages.length > 0) {
        setChatMessages(messages);
      } else {
        setChatMessages([
          { role: 'ai', content: "Hello! I'm your TradeFlow AI Orchestrator. How can I help you today? I can fetch news, analyze charts, or run backtests for you." }
        ]);
      }
    }, (error) => {
      handleFirestoreError(error, OperationType.LIST, 'chats');
    });

    return () => unsubscribe();
  }, [user]);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages]);

  const [activeAgent, setActiveAgent] = useState<AgentConfig>({
    id: '1',
    name: 'PPO-TrendMaster v2',
    type: 'pretrained',
    rewardStyle: 'balanced',
    riskTolerance: 0.4,
    holdingBehavior: 'short-term'
  });
  const [strategies, setStrategies] = useState<Strategy[]>([
    { id: '1', name: 'Trend Following', description: 'EMA Crossover & ADX filters', enabled: true },
    { id: '2', name: 'Mean Reversion', description: 'Bollinger Bands & RSI divergence', enabled: false },
    { id: '3', name: 'Volatility Breakout', description: 'ATR-based range expansion', enabled: true },
    { id: '4', name: 'Sentiment Analysis', description: 'Social media & News signals', enabled: false },
  ]);

  useEffect(() => {
    const loadData = async () => {
      const data = await fetchBinanceData(symbol, timeframe);
      if (data.length > 0) {
        setMarketData(data);
      } else {
        setMarketData(generateMockData(150));
      }
    };
    loadData();
  }, [symbol, timeframe]);

  // Fetch saved data from Firestore
  useEffect(() => {
    if (!user) return;

    const backtestsQuery = query(
      collection(db, 'backtests'),
      where('ownerId', '==', user.uid),
      orderBy('timestamp', 'desc'),
      limit(10)
    );

    const agentsQuery = query(
      collection(db, 'agents'),
      where('ownerId', '==', user.uid),
      orderBy('createdAt', 'desc')
    );

    const unsubBacktests = onSnapshot(backtestsQuery, (snapshot) => {
      setSavedBacktests(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
    }, (error) => handleFirestoreError(error, OperationType.LIST, 'backtests'));

    const unsubAgents = onSnapshot(agentsQuery, (snapshot) => {
      setSavedAgents(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() } as AgentConfig)));
    }, (error) => handleFirestoreError(error, OperationType.LIST, 'agents'));

    return () => {
      unsubBacktests();
      unsubAgents();
    };
  }, [user]);

  const saveAgent = async () => {
    if (!user) return;
    setIsSavingAgent(true);
    try {
      const agentData = {
        ...activeAgent,
        ownerId: user.uid,
        createdAt: new Date().toISOString()
      };
      await setDoc(doc(db, 'agents', activeAgent.id), agentData);
      setIsSavingAgent(false);
    } catch (error) {
      handleFirestoreError(error, OperationType.WRITE, 'agents');
      setIsSavingAgent(false);
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isChatLoading || !user) return;

    const userMsg = inputMessage;
    setInputMessage('');
    
    const saveMsg = async (role: 'user' | 'ai', content: string) => {
      try {
        await addDoc(collection(db, 'chats'), {
          role,
          content,
          userId: user.uid,
          createdAt: new Date().toISOString()
        });
      } catch (error) {
        handleFirestoreError(error, OperationType.CREATE, 'chats');
      }
    };

    await saveMsg('user', userMsg);
    setIsChatLoading(true);

    try {
      let response = await sendMessage(userMsg);
      let aiText = response.text || "I'm processing your request...";
      await saveMsg('ai', aiText);

      // Handle Tool Calls Loop
      let currentResponse = response;
      while (currentResponse.functionCalls && currentResponse.functionCalls.length > 0) {
        const toolResponses = [];
        
        for (const call of currentResponse.functionCalls) {
          const toolResult = await handleToolCall(call, { marketData });
          if (toolResult) {
            // Update UI state based on tool
            if (toolResult.data) setMarketData(toolResult.data);
            if (toolResult.result) {
              setBacktestResult(toolResult.result);
              setActiveAgent(toolResult.agent);
              setStrategies(toolResult.strategies);
              setActiveTab('backtest');
              setPlaybackIndex(0);
            }
            
            await saveMsg('ai', `[System]: ${toolResult.message}`);
            
            // Prepare response for the model
            toolResponses.push({
              functionResponse: {
                name: call.name,
                response: { result: toolResult.message, dataSummary: toolResult.data ? `First 5 candles: ${JSON.stringify(toolResult.data.slice(0, 5))}` : "Action completed" },
                id: call.id
              }
            });
          }
        }

        // Send tool results back to the model to get the final interpretation
        if (toolResponses.length > 0) {
          // We use the chat history to continue the thought
          currentResponse = await chat.sendMessage({
            message: toolResponses
          });
          
          if (currentResponse.text) {
            await saveMsg('ai', currentResponse.text!);
          }
        } else {
          break;
        }
      }
    } catch (error) {
      await saveMsg('ai', "Sorry, I encountered an error while processing your request.");
    } finally {
      setIsChatLoading(false);
    }
  };

  const startPlayback = () => {
    if (!backtestResult) return;
    setIsPlaybackRunning(true);
    playbackTimerRef.current = setInterval(() => {
      setPlaybackIndex(prev => {
        if (prev === undefined || prev >= marketData.length - 1) {
          clearInterval(playbackTimerRef.current!);
          setIsPlaybackRunning(false);
          return prev;
        }
        return prev + 1;
      });
    }, 50);
  };

  const stopPlayback = () => {
    if (playbackTimerRef.current) clearInterval(playbackTimerRef.current);
    setIsPlaybackRunning(false);
  };

  const resetPlayback = () => {
    stopPlayback();
    setPlaybackIndex(0);
  };

  useEffect(() => {
    return () => {
      if (playbackTimerRef.current) clearInterval(playbackTimerRef.current);
    };
  }, []);

  const runBacktest = async () => {
    setIsBacktesting(true);
    setPlaybackIndex(0);
    setTimeout(async () => {
      const result = executeBacktest(marketData, activeAgent, strategies.filter(s => s.enabled));
      setBacktestResult(result);
      setIsBacktesting(false);
      setActiveTab('backtest');

      // Save to Firestore if logged in
      if (user) {
        try {
          await addDoc(collection(db, 'backtests'), {
            id: Math.random().toString(36).substr(2, 9),
            ownerId: user.uid,
            agentId: activeAgent.id,
            symbol,
            timeframe,
            totalProfit: result.totalProfit,
            drawdown: result.drawdown,
            sharpeRatio: result.sharpeRatio,
            winRate: result.winRate,
            timestamp: new Date().toISOString()
          });
        } catch (error) {
          handleFirestoreError(error, OperationType.CREATE, 'backtests');
        }
      }
    }, 1500);
  };

  const runPaperTrade = async () => {
    setIsBacktesting(true);
    setPlaybackIndex(0);
    setTimeout(async () => {
      const result = executeBacktest(marketData, activeAgent, strategies.filter(s => s.enabled));
      setBacktestResult(result);
      setIsBacktesting(false);
      setActiveTab('paper');
    }, 1500);
  };

  if (loading) {
    return (
      <div className="h-screen w-screen bg-slate-950 flex items-center justify-center">
        <Activity className="w-12 h-12 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="h-screen w-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
        <div className="w-20 h-20 bg-indigo-600 rounded-2xl flex items-center justify-center mb-8 shadow-2xl shadow-indigo-500/20">
          <Zap className="w-12 h-12 text-white fill-white" />
        </div>
        <h1 className="text-4xl font-bold mb-4 tracking-tight">TradeFlow <span className="text-indigo-500">AI</span></h1>
        <p className="text-slate-400 max-w-md mb-8">
          The complete trading workflow platform for RL-based agents. Sign in to start backtesting and managing your agents.
        </p>
        <button 
          onClick={signIn}
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-3 rounded-xl font-bold transition-all shadow-xl shadow-indigo-500/20 flex items-center gap-3"
        >
          <LayoutDashboard className="w-5 h-5" />
          Sign in with Google
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-950 text-slate-50 overflow-hidden font-sans">
      {/* Sidebar */}
      <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col">
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Zap className="w-6 h-6 text-white fill-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">TradeFlow <span className="text-indigo-500">AI</span></h1>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-2">
          <NavItem 
            icon={<LayoutDashboard className="w-5 h-5" />} 
            label="Dashboard" 
            active={activeTab === 'dashboard'} 
            onClick={() => setActiveTab('dashboard')} 
          />
          <NavItem 
            icon={<Activity className="w-5 h-5" />} 
            label="Backtesting" 
            active={activeTab === 'backtest'} 
            onClick={() => setActiveTab('backtest')} 
          />
          <NavItem 
            icon={<Shield className="w-5 h-5" />} 
            label="Agents" 
            active={activeTab === 'agents'} 
            onClick={() => setActiveTab('agents')} 
          />
          <NavItem 
            icon={<Database className="w-5 h-5" />} 
            label="Market Data" 
            active={activeTab === 'data'} 
            onClick={() => setActiveTab('data')} 
          />
          <NavItem 
            icon={<Zap className="w-5 h-5" />} 
            label="Live Trading" 
            active={activeTab === 'live'} 
            onClick={() => setActiveTab('live')} 
          />
          <NavItem 
            icon={<Activity className="w-5 h-5" />} 
            label="Paper Trading" 
            active={activeTab === 'paper'} 
            onClick={() => setActiveTab('paper')} 
          />
        </nav>

        <div className="p-4 border-t border-slate-800 relative">
          <AnimatePresence>
            {showUserMenu && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute bottom-full left-4 right-4 mb-2 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden z-50"
              >
                <div className="p-2 space-y-1">
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-800 flex items-center gap-2">
                    <Settings className="w-4 h-4" />
                    Account Settings
                  </button>
                  <button className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-slate-800 flex items-center gap-2">
                    <Shield className="w-4 h-4" />
                    Security
                  </button>
                  <div className="h-px bg-slate-800 my-1" />
                  <button 
                    onClick={logout}
                    className="w-full text-left px-3 py-2 rounded-lg text-sm hover:bg-rose-500/10 text-rose-400 flex items-center gap-2"
                  >
                    <Plus className="w-4 h-4 rotate-45" />
                    Sign Out
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <button 
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="w-full bg-slate-800/50 rounded-lg p-4 flex items-center gap-3 hover:bg-slate-800 transition-colors"
          >
            <img 
              src={user.photoURL || `https://ui-avatars.com/api/?name=${user.displayName}`} 
              alt="Profile" 
              className="w-8 h-8 rounded-full"
              referrerPolicy="no-referrer"
            />
            <div className="flex-1 min-w-0 text-left">
              <p className="text-sm font-medium truncate">{user.displayName}</p>
              <p className="text-xs text-slate-400 truncate">Pro Plan</p>
            </div>
            <Settings className={cn("w-4 h-4 text-slate-400 transition-transform", showUserMenu && "rotate-90")} />
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-slate-950 relative">
        {/* Command Center Toggle */}
        <button 
          onClick={() => setShowCommandCenter(!showCommandCenter)}
          className="fixed bottom-8 right-8 w-14 h-14 bg-indigo-600 rounded-full flex items-center justify-center shadow-2xl shadow-indigo-500/40 z-50 hover:scale-110 transition-transform"
        >
          <MessageSquare className="w-6 h-6 text-white" />
          {isChatLoading && <div className="absolute inset-0 border-4 border-indigo-400 border-t-transparent rounded-full animate-spin" />}
        </button>

        {/* Command Center Panel */}
        <AnimatePresence>
          {showCommandCenter && (
            <motion.div 
              initial={{ opacity: 0, x: 300 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 300 }}
              className="fixed top-0 right-0 bottom-0 w-96 bg-slate-900 border-l border-slate-800 shadow-2xl z-40 flex flex-col"
            >
              <div className="p-6 border-b border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
                    <Zap className="w-5 h-5 text-white fill-white" />
                  </div>
                  <h3 className="font-bold">Command Center</h3>
                </div>
                <button onClick={() => setShowCommandCenter(false)} className="p-2 hover:bg-slate-800 rounded-lg transition-colors">
                  <Plus className="w-5 h-5 rotate-45 text-slate-500" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
                {chatMessages.map((msg, i) => (
                  <div key={i} className={cn(
                    "max-w-[85%] p-3 rounded-2xl text-sm",
                    msg.role === 'user' 
                      ? "bg-indigo-600 text-white ml-auto rounded-tr-none" 
                      : "bg-slate-800 text-slate-200 mr-auto rounded-tl-none border border-slate-700"
                  )}>
                    <div className="prose prose-invert prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
                {isChatLoading && (
                  <div className="bg-slate-800 text-slate-400 mr-auto rounded-2xl rounded-tl-none border border-slate-700 p-3 text-xs animate-pulse">
                    AI is thinking...
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <div className="p-4 border-t border-slate-800">
                <div className="relative">
                  <input 
                    type="text" 
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                    placeholder="Ask AI to analyze news or run tests..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 pr-12 text-sm outline-none focus:border-indigo-500 transition-colors"
                  />
                  <button 
                    onClick={handleSendMessage}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-indigo-500 hover:text-indigo-400"
                  >
                    <Send className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <header className="h-16 border-b border-slate-800 flex items-center justify-between px-8 sticky top-0 bg-slate-950/80 backdrop-blur-md z-10">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5">
              <Search className="w-4 h-4 text-slate-400" />
              <input 
                type="text" 
                value={symbol} 
                onChange={(e) => setSymbol(e.target.value)}
                className="bg-transparent border-none outline-none text-sm w-32"
                placeholder="Search symbol..."
              />
            </div>
            <select 
              value={timeframe} 
              onChange={(e) => setTimeframe(e.target.value as Timeframe)}
              className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-sm outline-none"
            >
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="1h">1h</option>
              <option value="1d">1d</option>
            </select>
          </div>

          <div className="flex items-center gap-3">
            <button 
              onClick={runBacktest}
              disabled={isBacktesting}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all shadow-lg shadow-indigo-500/20"
            >
              {isBacktesting ? (
                <Activity className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4 fill-current" />
              )}
              Run Backtest
            </button>
          </div>
        </header>

        <div className="p-8">
          <AnimatePresence mode="wait">
            {activeTab === 'dashboard' && (
              <motion.div 
                key="dashboard"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="space-y-8"
              >
                {/* Stats Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  <StatCard label="Current Price" value="$64,231.50" change="+2.4%" trend="up" />
                  <StatCard label="24h Volume" value="$2.4B" change="-0.8%" trend="down" />
                  <StatCard label="Market Cap" value="$1.2T" change="+1.2%" trend="up" />
                  <StatCard label="Volatility" value="4.2%" change="+0.5%" trend="up" />
                </div>

                {/* Main Chart */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <h3 className="text-lg font-semibold">{symbol} Price Chart</h3>
                      <p className="text-sm text-slate-400">Real-time data from {source}</p>
                    </div>
                    <div className="flex gap-2">
                      <button className="px-3 py-1 rounded-md bg-slate-800 text-xs font-medium border border-slate-700">Price</button>
                      <button className="px-3 py-1 rounded-md text-xs font-medium text-slate-400 hover:bg-slate-800">Volume</button>
                    </div>
                  </div>
                  <div className="h-[400px] w-full">
                    <CandlestickChart data={marketData} height={400} />
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                  {/* Agent Selection */}
                  <div className="lg:col-span-1 bg-slate-900 border border-slate-800 rounded-2xl p-6">
                    <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <Shield className="w-5 h-5 text-indigo-500" />
                      Active Agent
                    </h3>
                    <div className="space-y-4">
                      <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-semibold text-indigo-400">{activeAgent.name}</span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500 text-white uppercase">{activeAgent.type}</span>
                        </div>
                        <p className="text-xs text-slate-400 mb-4">Optimized for {activeAgent.rewardStyle} trading in high volatility markets.</p>
                        <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-500 uppercase font-bold">
                          <div>Reward: {activeAgent.rewardStyle}</div>
                          <div>Risk: {activeAgent.riskTolerance}</div>
                        </div>
                      </div>
                      <button 
                        onClick={() => setActiveTab('agents')}
                        className="w-full py-3 rounded-xl border border-slate-800 text-sm font-medium hover:bg-slate-800 transition-colors flex items-center justify-center gap-2"
                      >
                        <Plus className="w-4 h-4" />
                        Configure New Agent
                      </button>
                    </div>
                  </div>

                  {/* Strategy Pipeline */}
                  <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">
                    <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5 text-amber-500" />
                      Strategy Pipeline
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {strategies.map(s => (
                        <StrategyItem 
                          key={s.id}
                          name={s.name} 
                          desc={s.description} 
                          active={s.enabled} 
                          onClick={() => {
                            setStrategies(prev => prev.map(item => item.id === s.id ? { ...item, enabled: !item.enabled } : item));
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'backtest' && backtestResult && (
              <motion.div 
                key="backtest"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold">Backtest Results</h2>
                  <div className="flex gap-2">
                    <button className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800"><Download className="w-4 h-4" /></button>
                    <button className="p-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800"><Share2 className="w-4 h-4" /></button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                  <ResultCard label="Total Profit" value={`+${backtestResult.totalProfit}%`} color="text-emerald-400" />
                  <ResultCard label="Max Drawdown" value={`-${backtestResult.drawdown}%`} color="text-rose-400" />
                  <ResultCard label="Sharpe Ratio" value={backtestResult.sharpeRatio.toFixed(2)} color="text-indigo-400" />
                  <ResultCard label="Win Rate" value={`${backtestResult.winRate}%`} color="text-amber-400" />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                  <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-lg font-semibold">Performance Visualization</h3>
                      <div className="flex items-center gap-2">
                        <button 
                          onClick={isPlaybackRunning ? stopPlayback : startPlayback}
                          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-indigo-400 transition-all"
                        >
                          {isPlaybackRunning ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                        </button>
                        <button 
                          onClick={resetPlayback}
                          className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 transition-all"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                        <span className="text-xs font-mono text-slate-500">
                          {playbackIndex !== undefined ? `${Math.round((playbackIndex / marketData.length) * 100)}%` : '0%'}
                        </span>
                      </div>
                    </div>
                    <div className="h-[400px] w-full">
                      <CandlestickChart 
                        data={marketData} 
                        trades={backtestResult.trades} 
                        height={400} 
                        playbackIndex={playbackIndex}
                      />
                    </div>
                  </div>

                  <div className="lg:col-span-1 space-y-6">
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col">
                      <h3 className="text-lg font-semibold mb-4">Trade History</h3>
                      <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar max-h-[300px]">
                        {backtestResult.trades.length === 0 ? (
                          <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm">
                            <History className="w-8 h-8 mb-2 opacity-20" />
                            No trades executed
                          </div>
                        ) : (
                          backtestResult.trades.map(trade => (
                            <div key={trade.id} className="p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between">
                              <div className="flex items-center gap-3">
                                <div className={cn(
                                  "w-8 h-8 rounded-full flex items-center justify-center",
                                  trade.type === 'buy' ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"
                                )}>
                                  {trade.type === 'buy' ? <Plus className="w-4 h-4" /> : <ChevronRight className="w-4 h-4 rotate-90" />}
                                </div>
                                <div>
                                  <p className="text-xs font-bold uppercase">{trade.type}</p>
                                  <p className="text-[10px] text-slate-500">{new Date(trade.time).toLocaleDateString()}</p>
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="text-sm font-bold">${trade.price.toLocaleString()}</p>
                                {trade.profit !== undefined && (
                                  <p className={cn("text-[10px] font-bold", trade.profit >= 0 ? "text-emerald-400" : "text-rose-400")}>
                                    {trade.profit >= 0 ? '+' : ''}{trade.profit.toFixed(2)}
                                  </p>
                                )}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    </div>

                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                      <h3 className="text-lg font-semibold mb-4">Recent Backtests</h3>
                      <div className="space-y-2">
                        {savedBacktests.map(bt => (
                          <div key={bt.id} className="p-3 rounded-lg bg-slate-950 border border-slate-800 hover:bg-slate-800 transition-colors cursor-pointer">
                            <div className="flex justify-between items-center mb-1">
                              <span className="text-xs font-bold text-indigo-400">{bt.symbol}</span>
                              <span className={cn("text-xs font-bold", bt.totalProfit >= 0 ? "text-emerald-400" : "text-rose-400")}>
                                {bt.totalProfit >= 0 ? '+' : ''}{bt.totalProfit}%
                              </span>
                            </div>
                            <p className="text-[10px] text-slate-500">{new Date(bt.timestamp).toLocaleString()}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'agents' && (
              <motion.div 
                key="agents"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                className="max-w-4xl mx-auto space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold">Agent Configuration</h2>
                  <button 
                    onClick={saveAgent}
                    disabled={isSavingAgent}
                    className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2"
                  >
                    {isSavingAgent ? <Activity className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    Save Agent
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                  <div className="md:col-span-2 space-y-8">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      <div className="space-y-6">
                        <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                          <h3 className="text-lg font-semibold mb-4">Base Settings</h3>
                          <div className="space-y-4">
                            <div>
                              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Agent Name</label>
                              <input 
                                type="text" 
                                value={activeAgent.name}
                                onChange={(e) => setActiveAgent(prev => ({ ...prev, name: e.target.value }))}
                                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 outline-none focus:border-indigo-500 transition-colors"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Agent Type</label>
                              <div className="grid grid-cols-2 gap-2">
                                <button 
                                  onClick={() => setActiveAgent(prev => ({ ...prev, type: 'pretrained' }))}
                                  className={cn("py-2 rounded-lg text-sm font-medium border", activeAgent.type === 'pretrained' ? "bg-indigo-600 border-indigo-500" : "bg-slate-800 border-slate-700")}
                                >
                                  Pretrained
                                </button>
                                <button 
                                  onClick={() => setActiveAgent(prev => ({ ...prev, type: 'custom' }))}
                                  className={cn("py-2 rounded-lg text-sm font-medium border", activeAgent.type === 'custom' ? "bg-indigo-600 border-indigo-500" : "bg-slate-800 border-slate-700")}
                                >
                                  Custom
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                          <h3 className="text-lg font-semibold mb-4">RL Parameters</h3>
                          <div className="space-y-6">
                            <div>
                              <div className="flex justify-between mb-2">
                                <label className="text-xs font-bold text-slate-500 uppercase">Risk Tolerance</label>
                                <span className="text-xs font-bold text-indigo-400">{activeAgent.riskTolerance}</span>
                              </div>
                              <input 
                                type="range" min="0" max="1" step="0.1" 
                                value={activeAgent.riskTolerance}
                                onChange={(e) => setActiveAgent(prev => ({ ...prev, riskTolerance: parseFloat(e.target.value) }))}
                                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Reward Style</label>
                              <select 
                                value={activeAgent.rewardStyle}
                                onChange={(e) => setActiveAgent(prev => ({ ...prev, rewardStyle: e.target.value as any }))}
                                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 outline-none"
                              >
                                <option value="balanced">Balanced (Sharpe Ratio)</option>
                                <option value="aggressive">Aggressive (Total Profit)</option>
                                <option value="conservative">Conservative (Min Drawdown)</option>
                              </select>
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl">
                        <h3 className="text-lg font-semibold mb-4">Agent Preview</h3>
                        <div className="aspect-square bg-slate-950 rounded-xl border border-slate-800 flex items-center justify-center relative overflow-hidden">
                          <div className="absolute inset-0 opacity-20">
                            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-indigo-500 via-transparent to-transparent" />
                          </div>
                          <div className="z-10 text-center">
                            <div className="w-20 h-20 bg-indigo-600 rounded-3xl mx-auto mb-4 flex items-center justify-center shadow-2xl shadow-indigo-500/50">
                              <Shield className="w-10 h-10 text-white" />
                            </div>
                            <h4 className="text-xl font-bold">{activeAgent.name}</h4>
                            <p className="text-sm text-slate-400">Ready for deployment</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                    <h3 className="text-lg font-semibold mb-4">Saved Agents</h3>
                    <div className="space-y-3">
                      {savedAgents.length === 0 ? (
                        <p className="text-sm text-slate-500 text-center py-8">No saved agents yet</p>
                      ) : (
                        savedAgents.map(agent => (
                          <div 
                            key={agent.id} 
                            onClick={() => setActiveAgent(agent)}
                            className={cn(
                              "p-4 rounded-xl border transition-all cursor-pointer",
                              activeAgent.id === agent.id ? "bg-indigo-500/10 border-indigo-500/30" : "bg-slate-950 border-slate-800 hover:bg-slate-800"
                            )}
                          >
                            <div className="flex justify-between items-center mb-1">
                              <span className="text-sm font-bold">{agent.name}</span>
                              <span className="text-[10px] font-bold text-indigo-400 uppercase">{agent.type}</span>
                            </div>
                            <p className="text-[10px] text-slate-500">Risk: {agent.riskTolerance} • {agent.rewardStyle}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
            {activeTab === 'data' && (
              <motion.div 
                key="data"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold">Market Data Sources</h2>
                  <button className="bg-indigo-600 px-4 py-2 rounded-lg text-sm font-semibold flex items-center gap-2">
                    <Plus className="w-4 h-4" />
                    Add Source
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  <DataSourceCard 
                    name="Binance" 
                    status="Connected" 
                    latency="45ms" 
                    active={source === 'Binance'} 
                    onClick={() => setSource('Binance')}
                  />
                  <DataSourceCard 
                    name="Yahoo Finance" 
                    status="Available" 
                    latency="120ms" 
                    active={source === 'Yahoo Finance'} 
                    onClick={() => setSource('Yahoo Finance')}
                  />
                  <DataSourceCard 
                    name="Alpha Vantage" 
                    status="API Key Required" 
                    latency="-" 
                    active={source === 'Alpha Vantage'} 
                    onClick={() => setSource('Alpha Vantage')}
                  />
                  <DataSourceCard 
                    name="Polygon.io" 
                    status="Premium" 
                    latency="-" 
                    active={source === 'Polygon.io'} 
                    onClick={() => setSource('Polygon.io')}
                  />
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
                  <div className="p-6 border-b border-slate-800 flex items-center justify-between">
                    <h3 className="text-lg font-semibold">Raw Data Preview: {symbol}</h3>
                    <div className="flex gap-2">
                      <button className="px-3 py-1.5 rounded-lg bg-slate-800 text-xs font-medium border border-slate-700 flex items-center gap-2">
                        <Download className="w-3 h-3" />
                        Export CSV
                      </button>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-slate-950 text-slate-500 font-bold uppercase text-[10px] tracking-widest">
                        <tr>
                          <th className="px-6 py-4">Time</th>
                          <th className="px-6 py-4">Open</th>
                          <th className="px-6 py-4">High</th>
                          <th className="px-6 py-4">Low</th>
                          <th className="px-6 py-4">Close</th>
                          <th className="px-6 py-4">Volume</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {marketData.slice(-10).reverse().map((candle, i) => (
                          <tr key={i} className="hover:bg-slate-800/30 transition-colors">
                            <td className="px-6 py-4 font-mono text-xs">{new Date(candle.time).toLocaleString()}</td>
                            <td className="px-6 py-4">${candle.open.toFixed(2)}</td>
                            <td className="px-6 py-4 text-emerald-400">${candle.high.toFixed(2)}</td>
                            <td className="px-6 py-4 text-rose-400">${candle.low.toFixed(2)}</td>
                            <td className="px-6 py-4">${candle.close.toFixed(2)}</td>
                            <td className="px-6 py-4 text-slate-400">{candle.volume.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </motion.div>
            )}
            {activeTab === 'live' && (
              <motion.div 
                key="live"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="max-w-4xl mx-auto space-y-8"
              >
                <div className="bg-slate-900 border border-slate-800 rounded-3xl p-12 text-center space-y-6 relative overflow-hidden">
                  <div className="absolute inset-0 opacity-10">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-indigo-500 via-transparent to-transparent" />
                  </div>
                  
                  <div className="w-24 h-24 bg-indigo-600/20 rounded-full mx-auto flex items-center justify-center border border-indigo-500/30">
                    <Zap className="w-12 h-12 text-indigo-400 animate-pulse" />
                  </div>
                  
                  <div className="space-y-2">
                    <h2 className="text-3xl font-bold">Connect to Broker</h2>
                    <p className="text-slate-400 max-w-md mx-auto">
                      Ready to deploy your agent? Connect your preferred broker to start executing trades in real-time.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto">
                    <BrokerCard name="Binance" icon={<Database className="w-5 h-5" />} />
                    <BrokerCard name="Alpaca" icon={<Shield className="w-5 h-5" />} />
                    <BrokerCard name="IBKR" icon={<BarChart3 className="w-5 h-5" />} />
                  </div>

                  <div className="pt-6">
                    <button className="bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-3 rounded-xl font-bold transition-all shadow-xl shadow-indigo-500/20">
                      Enable Live Mode
                    </button>
                    <p className="text-[10px] text-slate-500 mt-4 uppercase tracking-widest font-bold">
                      Requires Pro Subscription & Verified API Keys
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
            {activeTab === 'paper' && (
              <motion.div 
                key="paper"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="space-y-8"
              >
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold">Paper Trading Simulation</h2>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => {
                        runPaperTrade();
                      }}
                      className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                    >
                      Start Session
                    </button>
                  </div>
                </div>

                {backtestResult && (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">
                      <h3 className="text-lg font-semibold mb-6">Session Performance</h3>
                      <div className="h-[400px] w-full">
                        <CandlestickChart 
                          data={marketData} 
                          trades={backtestResult.trades} 
                          height={400} 
                        />
                      </div>
                    </div>
                    <div className="lg:col-span-1 space-y-6">
                      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                        <h3 className="text-lg font-semibold mb-4">AI Reflection</h3>
                        <p className="text-sm text-slate-400 mb-4">
                          Ask the AI to analyze its performance in this session, identify mistakes, and store the learnings in its memory layer.
                        </p>
                        <button 
                          onClick={async () => {
                            setIsChatLoading(true);
                            try {
                              const reflection = await generateAIReflection(backtestResult, activeAgent);
                              if (user) {
                                await addDoc(collection(db, 'agent_memories'), {
                                  userId: user.uid,
                                  agentId: activeAgent.id,
                                  reflection,
                                  createdAt: new Date().toISOString()
                                });
                              }
                              setChatMessages(prev => [...prev, { role: 'ai', content: `**Reflection Complete:**\n\n${reflection}` }]);
                              setShowCommandCenter(true);
                            } catch (error) {
                              console.error(error);
                            } finally {
                              setIsChatLoading(false);
                            }
                          }}
                          className="w-full bg-slate-800 hover:bg-slate-700 text-white px-4 py-3 rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
                        >
                          <Brain className="w-5 h-5" />
                          Generate Reflection
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}

function BrokerCard({ name, icon }: { name: string, icon: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 hover:border-indigo-500/50 transition-all cursor-pointer group">
      <div className="w-10 h-10 rounded-lg bg-slate-900 flex items-center justify-center mx-auto mb-3 group-hover:bg-indigo-500/10 transition-colors">
        {icon}
      </div>
      <p className="text-sm font-bold">{name}</p>
    </div>
  );
}

function DataSourceCard({ name, status, latency, active, onClick }: { name: string, status: string, latency: string, active: boolean, onClick: () => void }) {
  return (
    <div 
      onClick={onClick}
      className={cn(
        "p-6 rounded-2xl border transition-all cursor-pointer relative overflow-hidden",
        active ? "bg-indigo-600/10 border-indigo-500/50" : "bg-slate-900 border-slate-800 hover:border-slate-700"
      )}
    >
      {active && <div className="absolute top-0 right-0 w-16 h-16 bg-indigo-500/10 blur-2xl -mr-8 -mt-8" />}
      <div className="flex items-center justify-between mb-4">
        <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center">
          <Database className={cn("w-5 h-5", active ? "text-indigo-400" : "text-slate-500")} />
        </div>
        <div className={cn(
          "px-2 py-0.5 rounded text-[10px] font-bold uppercase",
          status === 'Connected' ? "bg-emerald-500/10 text-emerald-400" : "bg-slate-800 text-slate-500"
        )}>
          {status}
        </div>
      </div>
      <h4 className="font-bold mb-1">{name}</h4>
      <p className="text-xs text-slate-500">Latency: {latency}</p>
    </div>
  );
}

function NavItem({ icon, label, active, onClick }: { icon: React.ReactNode, label: string, active?: boolean, onClick: () => void }) {
  return (
    <button 
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all",
        active 
          ? "bg-indigo-600/10 text-indigo-400 border border-indigo-500/20" 
          : "text-slate-400 hover:text-slate-100 hover:bg-slate-800/50"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function StatCard({ label, value, change, trend }: { label: string, value: string, change: string, trend: 'up' | 'down' }) {
  return (
    <div className="bg-slate-900 border border-slate-800 p-5 rounded-2xl shadow-lg">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <div className="flex items-end justify-between">
        <h4 className="text-2xl font-bold">{value}</h4>
        <span className={cn(
          "text-xs font-bold px-2 py-0.5 rounded-full flex items-center gap-1",
          trend === 'up' ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"
        )}>
          {trend === 'up' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {change}
        </span>
      </div>
    </div>
  );
}

function StrategyItem({ name, desc, active, onClick }: { name: string, desc: string, active: boolean, onClick?: () => void, key?: string | number }) {
  return (
    <div 
      onClick={onClick}
      className={cn(
        "p-4 rounded-xl border transition-all cursor-pointer",
        active ? "bg-slate-800 border-slate-700" : "bg-slate-900/50 border-slate-800 opacity-60 hover:opacity-100"
      )}
    >
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-semibold">{name}</span>
        <div className={cn("w-2 h-2 rounded-full", active ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : "bg-slate-700")} />
      </div>
      <p className="text-xs text-slate-500">{desc}</p>
    </div>
  );
}

function ResultCard({ label, value, color }: { label: string, value: string, color: string }) {
  return (
    <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl text-center">
      <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">{label}</p>
      <h4 className={cn("text-3xl font-black", color)}>{value}</h4>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
