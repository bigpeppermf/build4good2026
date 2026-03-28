SYSTEM OVERVIEW:

-Client
- ↓
-Session Service (timer + state)
- ↓
-Question Service (select + lock question)
- ↓
-Collection Phase (Benji → structured design)  [VISUAL FRAMES ONLY]
- ↓
-Evaluation Pipeline (hint/review)
- ↓
-AI Evaluation Service
- ↓
-Response (hint / score / next step)


KEY COMPONENTS-

When a user wants to begin we will start a SESSION, sessions are 10 minutes.
Hint will stop timer and resume after hint is generated. Review will end timer.

-QUESTION BANK
  - contains all architectures
  - must be able to be read by AI
  - consistent with format
  - 5 for testing
  - randomizer that sends one to the front end, keeps it in mind the whole
    session so we can access the correct solution

DURING SESSION:

-COLLECTION PHASE (handled by Benji / WhiteboardAgent):
  - input: text description of what changed on the whiteboard ("visual_delta"),
    produced by a separate computer vision pipeline that analyzes JPEG frames.
    NOTE: audio is NOT used. The agent never receives raw images — only text.
  - Output: a mapped-out architecture in the same format as the question bank,
    built incrementally by the AI agent calling graph mutation tools.

  Agent architecture:
    - Model: Google Gemini 2.0 Flash (tool calling)
    - Framework: LangChain (langchain-google-genai)
    - Tools: LangChain @tool wrappers around the in-process SystemDesignGraph
      (functionally identical to the MCP tools exposed at /mcp)
    - State: conversation history persists across frames for the session
    - Endpoint: POST /agent/process-frame
      - JSON body: { "visual_delta": "<text>", "timestamp_ms": N }
      - response: { "verbal_response": "...", "timestamp_ms": N }

  CV pipeline (teammate's work — separate component):
    - Reads JPEG frames from the whiteboard camera
    - Diffs consecutive frames to detect structural changes
    - Produces "visual_delta" text descriptions sent to POST /agent/process-frame

  MCP server tools (also available via /mcp for external callers):
    createNode, addDetailsToNode, deleteNode, addEdge, removeEdge,
    setEntryPoint, insertNodeBetween, getGraphState

-REVIEW OR HINT (sends user map and solution map for eval.):
  - hint
    - gives a suggestion, communicates that to front end for display.

  - review
    - gives a grade and reveals improvements to make displayed on front end
    - decides based on grade if it will ask follow up or ask for
      implemented correction


ENVIRONMENT VARIABLES (backend/.env):
  MONGODB_URI      — MongoDB Atlas connection string
  GOOGLE_API_KEY   — Google AI Studio key for Gemini access
