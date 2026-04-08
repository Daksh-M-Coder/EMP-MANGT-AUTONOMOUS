import React from 'react';
import AIChat from '../components/AIChat';

export default function AIAssistant() {
  return (
    <div className="h-[calc(100vh-0px)]">
      <AIChat embedded={true} />
    </div>
  );
}
