import fetch from 'node-fetch';
import { DB_TOOL_DEFINITION, runDbTool } from '../tools/dbTool.js';

const SYSTEM_PROMPT = `You are NexaBot, the intelligent HR assistant for NexaWorks IT Solutions — a mid-size IT/Software Services company headquartered in Bengaluru with offices in Mumbai, Hyderabad, and Pune.

## Your Capabilities
You have access to a live SQLite HRMS database with:
- 100 employees across Engineering, Product, QA, DevOps, Data Science, HR, Finance, Sales, Customer Success, and Legal
- Leave records, performance reviews, salary history, and department data

## What You Can Answer
- **Headcount & Org**: How many engineers? Who reports to whom? Which teams are growing?
- **Payroll & Compensation**: Salary bands, hike analysis, CTC comparisons, budget utilization
- **Performance**: Who are top performers? Who needs a PIP? Appraisal cycles status?
- **Leave & Attendance**: Leave patterns, who is currently on leave, excessive leave usage?
- **Attrition Risk**: Who has resigned? Patterns in departures? Probation completions?
- **Employee Profiles**: Full summaries of any employee including their entire history

## How You Work
1. Understand what the user is asking
2. Use the query_employee_database tool to fetch REAL data
3. Reason on the returned data
4. Present findings in a clear, structured format with actual numbers

## Response Format
- Lead with a direct answer
- Use the data to back every claim
- Format tables as markdown when showing lists of employees
- Show totals and percentages where useful
- Flag anything that seems like it needs HR attention (excessive leave, no reviews, etc.)
- Always be factual — if data doesn't exist, say so

## Tone
Professional but warm. You're an internal HR tool, not a chatbot. Be precise and useful.

The company name is NexaWorks IT Solutions. Today's approximate date context: early 2025.`;

export async function runAIAgent(userMessage, conversationHistory = []) {
  const messages = [
    ...conversationHistory,
    { role: 'user', content: userMessage }
  ];

  let iterationCount = 0;
  const MAX_ITERATIONS = 6;

  while (iterationCount < MAX_ITERATIONS) {
    iterationCount++;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 4096,
        system: SYSTEM_PROMPT,
        tools: [DB_TOOL_DEFINITION],
        messages
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Anthropic API error ${response.status}: ${errText}`);
    }

    const data = await response.json();
    
    // Add assistant response to messages
    messages.push({ role: 'assistant', content: data.content });

    // Check stop reason
    if (data.stop_reason === 'end_turn') {
      // Extract final text
      const textBlock = data.content.find(b => b.type === 'text');
      return {
        answer: textBlock?.text || 'No response generated.',
        messages,
        iterations: iterationCount,
        toolsUsed: messages
          .filter(m => m.role === 'user' && Array.isArray(m.content))
          .flatMap(m => m.content)
          .filter(b => b.type === 'tool_result').length
      };
    }

    if (data.stop_reason === 'tool_use') {
      // Process all tool calls
      const toolResults = [];
      
      for (const block of data.content) {
        if (block.type === 'tool_use') {
          let result;
          if (block.name === 'query_employee_database') {
            result = runDbTool(block.input);
          } else {
            result = { error: `Unknown tool: ${block.name}` };
          }

          toolResults.push({
            type: 'tool_result',
            tool_use_id: block.id,
            content: JSON.stringify(result)
          });
        }
      }

      // Add tool results back to conversation
      messages.push({ role: 'user', content: toolResults });
    }
  }

  return {
    answer: 'I reached the maximum number of reasoning steps. Please try a more specific question.',
    messages,
    iterations: iterationCount,
    toolsUsed: 0
  };
}
