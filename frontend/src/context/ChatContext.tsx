import React, { createContext, useContext, useState, ReactNode } from 'react';
import { api } from '../services/api';

interface Message {
  role: 'user' | 'agent';
  content: string;
}

interface ChatContextType {
  isOpen: boolean;
  toggleDrawer: () => void;
  messages: Message[];
  sendMessage: (msg: string) => Promise<void>;
  isLoading: boolean;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: 'agent', content: 'Hi! I am your AI CRM Assistant. How can I help you today?' }
  ]);
  const [isLoading, setIsLoading] = useState(false);

  const toggleDrawer = () => setIsOpen(!isOpen);

  const sendMessage = async (msg: string) => {
    if (!msg.trim()) return;
    
    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setIsLoading(true);
    
    try {
      // The agent acts as whoever is logged in: send their own token so the
      // backend applies that person's role permissions to every tool call.
      const token = localStorage.getItem('staff_token') || localStorage.getItem('customer_token');
      if (!token) {
        setMessages(prev => [...prev, { role: 'agent', content: 'Please log in first.' }]);
        return;
      }

      const response = await api.post(
        '/ai/chat',
        { message: msg },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setMessages(prev => [...prev, { role: 'agent', content: response.data.response }]);
    } catch (error: any) {
      console.error('Error sending message:', error);
      const errorMsg = error?.response?.data?.detail || 'Sorry, I encountered an error communicating with the server.';
      setMessages(prev => [...prev, { role: 'agent', content: typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg) }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <ChatContext.Provider value={{ isOpen, toggleDrawer, messages, sendMessage, isLoading }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
