const fs = require('fs');
const https = require('https');
const { Anthropic } = require('@anthropic-ai/sdk');

// Initialize the Anthropic Client with secure credentials
const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

// Secure HTTPS wrapper to query the GitHub REST API without network clashes
async function githubAPI(endpoint, method = 'GET', body = null) {
  return new Promise((resolve, reject) => {
    // Sanitize and normalize path links to stop URL and DNS crashes
    const safePath = encodeURI(endpoint);
    const cleanPath = safePath.replace('https://github.com', '');
    const finalPath = cleanPath.startsWith('/') ? cleanPath : '/' + cleanPath;
    
    const options = {
      hostname: '://github.com',
      path: finalPath,
      method: method,
      headers: {
        'User-Agent': 'Central-Claude-Agent-Engine',
        'Authorization': `token ${process.env.AGENT_GITHUB_TOKEN}`,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data ? JSON.parse(data) : {});
        } else {
          reject(new Error(`GitHub REST API Failure (${res.statusCode}): ${data}`));
        }
      });
    });

    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function main() {
  const repo = process.env.TARGET_REPO;
  const file = process.env.TARGET_FILE;
  
  console.log(`📡 [LOG] Establishing connection matrix with repository: ${repo}`);
  console.log(`📄 [LOG] Target node mapping: ${file}`);

  let currentCode = "";
  let fileSHA = null;

  // Attempt to extract the codebase file context from the target workspace
  try {
    const fileData = await githubAPI(`/repos/${repo}/contents/${file}`);
    currentCode = Buffer.from(fileData.content, 'base64').toString('utf-8');
    fileSHA = fileData.sha;
    console.log("📥 [SUCCESS] Existing codebase context loaded safely into short-term memory.");
  } catch (err) {
    console.log("ℹ️ [INFO] Target script node does not exist. Preparing to build fresh logic architecture.");
  }

  console.log("🧠 [AI RUN] Streaming environment variables and prompts to Claude...");
  
  const response = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 4000,
    system: "You are an expert full-stack engineer, an IBM Data Scientist, and a conversion-driven Digital Marketer. Write production-ready, clean, data-efficient code. Return ONLY the raw file contents. Do not include markdown wraps, conversational introductions, or summary commentary.",
    messages: [
      { role: "user", content: `Existing File Contents:\n${currentCode}\n\nTask Objective:\n${process.env.USER_PROMPT}` }
    ]
  });

  const optimizedCode = response.content[0].text.trim();
  
  const commitBody = {
    message: `🔧 [AI Optimization] Core engine patch applied cleanly to ${file}`,
    content: Buffer.from(optimizedCode).toString('base64'),
    sha: fileSHA || undefined
  };

  console.log("📤 [PUSH] Committing modified data models back into the remote project main stream...");
  await githubAPI(`/repos/${repo}/contents/${file}`, 'PUT', commitBody);
  console.log(`🎉 [COMPLETE] Success! System deployed cleanly to ${repo}/${file}`);
}

main().catch(err => {
  console.error("❌ [CRITICAL CRASH] Run Failure:", err.message);
  process.exit(1);
});

