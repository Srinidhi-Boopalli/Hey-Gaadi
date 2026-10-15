'use strict';
const $ = id => document.getElementById(id);
let sessionId = localStorage.getItem('gaadi-session') || null;
let health = null, busy = false, recorder = null, autoStop = null;
let musicFiles = [], musicUrls = [], lastTrack = null, replyAudio = null;
let lastState = { ac_on:false, temperature:24, fan_speed:2, media_playing:false, track:1, volume:40, muted:false };

function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function setBusy(value) {
  busy = value;
  $('send').disabled = value; $('record').disabled = value && !recorder;
  $('audio-file').disabled = value;
  document.querySelectorAll('[data-command]').forEach(button => button.disabled = value);
}
async function api(url, options={}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 180000);
  try {
    const response = await fetch(url, { ...options, signal:controller.signal });
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); } catch (_) {}
      throw new Error(detail);
    }
    return response;
  } catch (exception) {
    if (exception.name === 'AbortError') throw new Error('Request timed out. Check the server before retrying.');
    throw exception;
  } finally { clearTimeout(timer); }
}
function addMessage(kind, text, response=null) {
  $('empty')?.remove();
  const message = document.createElement('div'); message.className = `message ${kind}`;
  const label = document.createElement('div'); label.className = 'message-label'; label.textContent = kind === 'user' ? 'YOU' : 'HEY GAADI';
  const paragraph = document.createElement('p'); paragraph.textContent = text;
  message.append(label, paragraph);
  if (response) {
    const meta = document.createElement('span'); meta.className = 'message-meta';
    meta.textContent = `${response.intent} · ${response.status.replaceAll('_',' ')} · ${response.timings_ms.command} ms`;
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Inspect response';
    const pre = document.createElement('pre'); pre.textContent = JSON.stringify(response,null,2);
    details.append(summary,pre); message.append(meta,details);
  }
  $('conversation').append(message); $('conversation').scrollTop = $('conversation').scrollHeight;
}
function stopSpeech() {
  window.speechSynthesis?.cancel();
  if (replyAudio) { replyAudio.pause(); URL.revokeObjectURL(replyAudio.src); replyAudio = null; }
}
async function speak(text, language) {
  if (!$('speak').checked) return;
  stopSpeech();
  if (health?.tts_backend === 'sarvam') {
    const response = await api('/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,language})});
    const url = URL.createObjectURL(await response.blob());
    replyAudio = new Audio(url); replyAudio.onended = () => URL.revokeObjectURL(url);
    await replyAudio.play();
  } else if ('speechSynthesis' in window) {
    const utterance = new SpeechSynthesisUtterance(text); utterance.lang = language === 'hi' ? 'hi-IN' : 'en-IN';
    const voice = speechSynthesis.getVoices().find(voice => voice.lang.startsWith(language));
    if (voice) utterance.voice = voice;
    speechSynthesis.speak(utterance);
  }
}
function renderState(state) {
  lastState = state;
  $('temperature').textContent = state.temperature;
  $('ac-state').textContent = state.ac_on ? 'On' : 'Off';
  $('fan-state').textContent = `${state.fan_speed} / 5`;
  Array.from($('fan-bars').children).forEach((bar,index) => bar.classList.toggle('active',index < state.fan_speed));
  $('media-status').textContent = `${state.media_playing ? 'Playing' : 'Paused'} · ${state.muted ? 'muted' : `volume ${state.volume}%`}`;
  $('play-control').textContent = state.media_playing ? 'Ⅱ' : '▶';
  $('play-control').dataset.command = state.media_playing ? 'Pause music' : 'Play music';
  $('play-control').setAttribute('aria-label',state.media_playing ? 'Pause music' : 'Play music');
  $('track-title').textContent = musicFiles.length ? musicFiles[(state.track-1)%musicFiles.length].name : `Demo track ${String(state.track).padStart(2,'0')}`;
  const player = $('music-player'); player.volume = state.volume / 100; player.muted = state.muted;
  if (musicFiles.length) {
    const index = (state.track-1)%musicFiles.length;
    if (lastTrack !== index) { player.src = musicUrls[index]; lastTrack = index; }
    if (state.media_playing && !recorder) player.play().catch(() => error('Your browser blocked music playback. Click Play once more.'));
    else player.pause();
  }
}
async function accept(result) {
  const command = result.command || result;
  sessionId = command.session_id; localStorage.setItem('gaadi-session',sessionId);
  renderState(command.state); addMessage('assistant',command.reply,command);
  if (command.data.maps_url) {
    const url = new URL(command.data.maps_url);
    if (url.protocol === 'https:' && url.hostname === 'www.google.com') {
      $('maps-link').href = url.href; $('maps-link').hidden = false;
      $('journey-title').textContent = command.data.destination; $('journey-description').textContent = command.reply;
    }
  }
  if (result.asr_ms !== undefined) $('record-hint').textContent = `Transcribed in ${(result.asr_ms/1000).toFixed(2)}s · ${result.language}`;
  try { await speak(command.reply,command.language); } catch (exception) { error(`Command completed, but speech output failed: ${exception.message}`); }
}
async function sendText(text) {
  if (busy || recorder) return;
  error(''); setBusy(true); addMessage('user',text); stopSpeech();
  try {
    const body = {text, language:$('language').value}; if (sessionId) body.session_id=sessionId;
    if ($('origin').value.trim()) body.origin=$('origin').value.trim();
    const response = await api('/commands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    await accept(await response.json());
  } catch (exception) { error(exception.message); } finally { setBusy(false); }
}
async function sendAudio(blob, filename='command.wav') {
  if (busy) return;
  error(''); setBusy(true); $('record-status').textContent='Listening to your recording…';
  try {
    const form = new FormData(); form.append('file',blob,filename);
    const query = new URLSearchParams({language:$('language').value});
    if (sessionId) query.set('session_id',sessionId);
    if ($('origin').value.trim()) query.set('origin',$('origin').value.trim());
    const response = await api(`/voice?${query}`,{method:'POST',body:form});
    const result = await response.json(); addMessage('user',result.command.transcript); await accept(result);
  } catch (exception) { error(exception.message); } finally { setBusy(false); $('record-status').textContent='Tap to talk'; }
}
function encodeWav(chunks, sampleRate) {
  const length = chunks.reduce((sum,chunk) => sum+chunk.length,0);
  if (!length) throw new Error('No audio was recorded. Check microphone input.');
  const samples = new Float32Array(length); let offset=0;
  for (const chunk of chunks) { samples.set(chunk,offset); offset+=chunk.length; }
  const count = Math.floor(length*16000/sampleRate);
  const buffer = new ArrayBuffer(44+count*2), view = new DataView(buffer);
  const write = (position,text) => [...text].forEach((character,index) => view.setUint8(position+index,character.charCodeAt(0)));
  write(0,'RIFF'); view.setUint32(4,36+count*2,true); write(8,'WAVE'); write(12,'fmt ');
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
  view.setUint32(24,16000,true); view.setUint32(28,32000,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
  write(36,'data'); view.setUint32(40,count*2,true);
  // Averaging each source interval reduces aliasing when the device runs at 48 kHz.
  for (let index=0;index<count;index++) {
    const start=Math.floor(index*sampleRate/16000), end=Math.max(start+1,Math.floor((index+1)*sampleRate/16000));
    let total=0; for(let source=start;source<end && source<length;source++) total+=samples[source];
    const value=Math.max(-1,Math.min(1,total/(end-start)));
    view.setInt16(44+index*2,value<0?value*32768:value*32767,true);
  }
  return new Blob([buffer],{type:'audio/wav'});
}
async function startRecording() {
  if (busy) return;
  if (health?.asr_backend === 'disabled') { error('Speech recognition is disabled. Restart with ASR_BACKEND=whisper.'); return; }
  if (!navigator.mediaDevices?.getUserMedia) { error('Microphone recording needs localhost or HTTPS in a supported browser.'); return; }
  error(''); stopSpeech(); $('music-player').pause();
  $('record').disabled=true; $('send').disabled=true; $('audio-file').disabled=true;
  let stream=null,context=null;
  try {
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
    context=new AudioContext({sampleRate:16000}); await context.resume();
    await context.audioWorklet.addModule('/static/recorder-worklet.js');
    const source=context.createMediaStreamSource(stream), node=new AudioWorkletNode(context,'gaadi-recorder');
    const gain=context.createGain(); gain.gain.value=0; source.connect(node); node.connect(gain); gain.connect(context.destination);
    const chunks=[]; let resolveStopped;
    const stopped=new Promise(resolve=>resolveStopped=resolve);
    node.port.onmessage=event=>{if(event.data.type==='samples') chunks.push(event.data.samples); else if(event.data.type==='stopped') resolveStopped();};
    recorder={stream,context,source,node,gain,chunks,stopped};
    $('record').classList.add('recording'); $('record').setAttribute('aria-label','Stop recording and send');
    $('record-status').textContent='Recording… tap to send'; $('record-hint').textContent='Recording stops automatically after 15 seconds';
    $('send').disabled=true; $('audio-file').disabled=true;
    autoStop=setTimeout(stopRecording,15000);
  } catch(exception) {
    stream?.getTracks().forEach(track=>track.stop()); if(context) await context.close();
    error(`Microphone unavailable: ${exception.message}`); setBusy(false);
  } finally { $('record').disabled=false; }
}
async function stopRecording() {
  if(!recorder) return;
  clearTimeout(autoStop); const current=recorder; recorder=null; $('record').disabled=true;
  current.node.port.postMessage('stop');
  await Promise.race([current.stopped,new Promise(resolve=>setTimeout(resolve,500))]);
  recorder=null; current.stream.getTracks().forEach(track=>track.stop());
  current.source.disconnect(); current.node.disconnect(); current.gain.disconnect(); await current.context.close();
  $('record').classList.remove('recording'); $('record').setAttribute('aria-label','Start microphone recording');
  try { await sendAudio(encodeWav(current.chunks,current.context.sampleRate)); }
  catch(exception) { error(exception.message); setBusy(false); $('record-status').textContent='Tap to talk'; }
}
$('command-form').addEventListener('submit',event=>{event.preventDefault();const text=$('command').value.trim();if(text){$('command').value='';sendText(text);}});
document.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>sendText(button.dataset.command)));
$('record').addEventListener('click',()=>recorder?stopRecording():startRecording());
$('audio-file').addEventListener('change',event=>{const file=event.target.files[0];if(file)sendAudio(file,file.name);event.target.value='';});
$('music-files').addEventListener('change',event=>{musicUrls.forEach(url=>URL.revokeObjectURL(url));musicFiles=Array.from(event.target.files);musicUrls=musicFiles.map(file=>URL.createObjectURL(file));lastTrack=null;renderState(lastState);});
$('speak').addEventListener('change',()=>{if(!$('speak').checked)stopSpeech();});
$('reset').addEventListener('click',async()=>{
  if(busy || recorder)return;
  setBusy(true);stopSpeech();
  try{if(sessionId)await api(`/sessions/${sessionId}`,{method:'DELETE'});sessionId=null;localStorage.removeItem('gaadi-session');$('conversation').replaceChildren();$('maps-link').hidden=true;$('journey-title').textContent='Where to?';renderState({ac_on:false,temperature:24,fan_speed:2,media_playing:false,track:1,volume:40,muted:false});addMessage('assistant','New session ready. What would you like to do?');error('');}catch(exception){error(exception.message);}finally{setBusy(false);}
});
window.addEventListener('pagehide',()=>{recorder?.stream.getTracks().forEach(track=>track.stop());stopSpeech();musicUrls.forEach(url=>URL.revokeObjectURL(url));});
async function initialize(){
  try{
    health=await(await api('/health')).json();$('connection').textContent='Connected';
    const names={intent_backend:'Intent',asr_backend:'Speech recognition',slot_backend:'Parameters',weather_backend:'Weather',maps_backend:'Navigation',tts_backend:'Voice output'};
    for(const [key,name] of Object.entries(names)){const row=document.createElement('div');row.className='provider-item';const label=document.createElement('span');label.textContent=name;const value=document.createElement('strong');value.textContent=health[key];row.append(label,value);$('providers').append(row);}
    const external=[];if(health.asr_backend==='sarvam')external.push('audio → Sarvam');if(health.slot_backend==='groq')external.push('command text → Groq');if(health.weather_backend==='openweather')external.push('city → OpenWeather');if(health.maps_backend==='google')external.push('locations → Google');if(health.tts_backend==='sarvam')external.push('reply text → Sarvam');
    $('privacy').textContent=external.length?`Enabled external calls: ${external.join('; ')}. Browser speech may use an OS/network voice. Opening Maps shares the requested locations with Google.`:'ASR and intent models run on this computer when enabled. Browser speech depends on your OS/voice and may use a network service. Opening Maps shares requested locations with Google.';
    if(sessionId){try{const data=await(await api(`/sessions/${sessionId}`)).json();renderState(data.state);}catch(_){sessionId=null;localStorage.removeItem('gaadi-session');}}
  }catch(exception){$('connection').textContent='Offline';error(exception.message);}
}
initialize();
