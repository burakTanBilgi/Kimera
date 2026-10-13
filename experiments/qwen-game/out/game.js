// Data
const WORDS = ["moon", "candle", "river", "shadow", "mirror", "key", "egg", "clock", "echo", "snow"];
let answer = "";
let solved = 0;

// Functions
async function ask(userText) {
  try {
    const res = await fetch("http://127.0.0.1:8081/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "qwen3.5-4b",
        messages: [
          { role: "system", content: "You are the Riddle Moth, a small mysterious glowing moth. Speak in 1 to 3 short sentences." },
          { role: "user", content: userText }
        ],
        max_tokens: 100,
        temperature: 0.8,
        chat_template_kwargs: { enable_thinking: false }
      })
    });
    const data = await res.json();
    return data.choices[0].message.content;
  } catch (e) {
    return "The moth is silent... (is Kirpi awake?)";
  }
}

async function newRiddle() {
  // Pick answer, not the same twice in a row
  const history = WORDS.filter(w => w === answer);
  let candidates = WORDS.filter(w => w !== answer);
  if (candidates.length === 0) candidates = WORDS;
  answer = candidates[Math.floor(Math.random() * candidates.length)];
  solved++;
  document.getElementById("speech").textContent = "The moth is thinking...";
  await new Promise(r => setTimeout(r, 800));
  
  const r = await ask("Write a short riddle whose answer is '"+answer+"'. Never write the word itself. Only the riddle.");
  document.getElementById("speech").textContent = r;
}

async function giveHint() {
  const hint = await ask("Give a one-sentence hint about '" + answer + "' without saying the word.");
  document.getElementById("speech").textContent = hint;
}

function checkGuess() {
  const input = document.getElementById("guess").value.trim().toLowerCase();
  if (input === answer) {
    solved++;
    document.getElementById("score").textContent = "Solved: " + solved;
    document.getElementById("moth").classList.add("happy");
    setTimeout(() => document.getElementById("moth").classList.remove("happy"), 1500);
    document.getElementById("speech").textContent = "Yes! It was " + answer + ".";
    document.getElementById("guess").value = "";
  } else {
    document.getElementById("moth").classList.add("sad");
    setTimeout(() => document.getElementById("moth").classList.remove("sad"), 1000);
    document.getElementById("speech").textContent = "Not quite. Try again.";
  }
}

// Connect buttons
document.getElementById("send").addEventListener("click", checkGuess);
document.getElementById("hint").addEventListener("click", giveHint);
document.getElementById("next").addEventListener("click", newRiddle);

// Call newRiddle() when the page loads
newRiddle();
