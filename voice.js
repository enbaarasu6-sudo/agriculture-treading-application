(function(){
  const root=document.getElementById('voiceAssistant');
  if(!root) return;
  const panel=root.querySelector('.voice-panel'), status=root.querySelector('.voice-status'), log=root.querySelector('.voice-log'), input=root.querySelector('.voice-input');
  const btn=root.querySelector('.voice-main'), send=root.querySelector('.voice-send'), close=root.querySelector('.voice-close');
  const langMap={en:'en-IN',ta:'ta-IN',hi:'hi-IN'};
  let recognition=null, listening=false;
  const lang=document.body.dataset.language||'en';
  function add(who,text){const p=document.createElement('p');p.className=who;p.textContent=text;log.appendChild(p);log.scrollTop=log.scrollHeight;}
  function speak(text){if(!('speechSynthesis' in window))return; speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(text); u.lang=langMap[lang]||'en-IN'; speechSynthesis.speak(u);}
  async function ask(text){text=(text||'').trim();if(!text)return;add('user',text);input.value='';status.textContent=lang==='ta'?'சிந்திக்கிறது...':lang==='hi'?'सोच रहा हूँ...':'Thinking...';
    try{const r=await fetch('/voice-chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text,language:lang})});const d=await r.json();add('assistant',d.reply);speak(d.reply);if(d.url)setTimeout(()=>location.href=d.url,700);}catch(e){const m=lang==='ta'?'இணைப்பு பிழை. மீண்டும் முயற்சிக்கவும்.':lang==='hi'?'कनेक्शन में समस्या है। फिर से कोशिश करें.':'Connection problem. Please try again.';add('assistant',m);speak(m);}status.textContent=lang==='ta'?'பேச கிளிக் செய்யவும்':lang==='hi'?'बोलने के लिए क्लिक करें':'Tap the mic and speak';}
  function start(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){status.textContent=lang==='ta'?'இந்த உலாவியில் குரல் உள்ளீடு இல்லை.':lang==='hi'?'इस ब्राउज़र में वॉइस इनपुट उपलब्ध नहीं है.':'Voice input is not available in this browser.';return;} if(listening){recognition.stop();return;} recognition=new SR();recognition.lang=langMap[lang]||'en-IN';recognition.interimResults=false;recognition.maxAlternatives=1;recognition.onstart=()=>{listening=true;btn.classList.add('recording');status.textContent=lang==='ta'?'கேட்கிறேன்...':lang==='hi'?'सुन रहा हूँ...':'Listening...';};recognition.onresult=e=>ask(e.results[0][0].transcript);recognition.onerror=()=>{status.textContent=lang==='ta'?'மீண்டும் முயற்சிக்கவும்.':lang==='hi'?'फिर से कोशिश करें.':'Please try again.';};recognition.onend=()=>{listening=false;btn.classList.remove('recording');};recognition.start();}
  btn.addEventListener('click',()=>{panel.classList.toggle('open');if(panel.classList.contains('open')) input.focus();});
  root.querySelector('.voice-mic').addEventListener('click',start);
  send.addEventListener('click',()=>ask(input.value)); input.addEventListener('keydown',e=>{if(e.key==='Enter')ask(input.value);}); close.addEventListener('click',()=>panel.classList.remove('open'));
})();
