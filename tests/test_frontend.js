// Pure audio-format checks; browser interaction is verified separately.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8');
const start = source.indexOf('function encodeWav(');
const end = source.indexOf('async function startRecording()',start);
const encodeWav = new Function(source.slice(start,end)+'; return encodeWav;')();

async function main() {
  for(const rate of [16000,48000]) {
    const samples = new Float32Array(rate).fill(.2);
    const blob = encodeWav([samples],rate);
    const bytes = await blob.arrayBuffer(), view = new DataView(bytes);
    assert.equal(bytes.byteLength,32044);
    assert.equal(view.getUint32(24,true),16000);
    assert.equal(view.getUint16(22,true),1);
    assert.equal(view.getUint16(34,true),16);
    assert.equal(view.getUint32(40,true),32000);
    assert(view.getInt16(44,true)>0);
  }
  assert.throws(()=>encodeWav([],16000));
  let Recorder;
  class Base { constructor(){this.events=[];this.port={postMessage:event=>this.events.push(event)};} }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../app/static/recorder-worklet.js'),'utf8'), {
    AudioWorkletProcessor:Base, Float32Array,
    registerProcessor:(name,processor)=>{assert.equal(name,'gaadi-recorder');Recorder=processor;}
  });
  const recorder=new Recorder();recorder.process([[new Float32Array(128)]]);
  assert.equal(recorder.events[0].samples.length,128);
  recorder.port.onmessage({data:'stop'});recorder.process([[new Float32Array(128)]]);
  assert.equal(recorder.events.length,2);assert.equal(recorder.events[1].type,'stopped');
  console.log('Frontend audio checks passed: 16/48 kHz input, WAV headers, empty input, worklet stop.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
