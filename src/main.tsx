import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';

// Global error filter to suppress MetaMask-related noise
window.addEventListener('error', (event) => {
  if (event.message && (event.message.includes('MetaMask') || event.message.includes('ethereum'))) {
    event.stopImmediatePropagation();
    event.preventDefault();
  }
}, true);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
