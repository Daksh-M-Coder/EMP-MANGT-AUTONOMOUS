import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/layout/Sidebar';
import Dashboard from './pages/Dashboard';
import Employees from './pages/Employees';
import EmployeeDetail from './pages/EmployeeDetail';
import AIAssistant from './pages/AIAssistant';
import Departments from './pages/Departments';
import Drafts from './pages/Drafts';

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 ml-60 overflow-y-auto bg-[#f8f7ff]">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/employees" element={<Employees />} />
          <Route path="/employees/:id" element={<EmployeeDetail />} />
          <Route path="/ai" element={<AIAssistant />} />
          <Route path="/departments" element={<Departments />} />
          <Route path="/drafts" element={<Drafts />} />
        </Routes>
      </main>
    </div>
  );
}
