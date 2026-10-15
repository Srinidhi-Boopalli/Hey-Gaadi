class GaadiRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.active = true;
    this.port.onmessage = event => {
      if (event.data === 'stop') {
        this.active = false;
        this.port.postMessage({ type: 'stopped' });
      }
    };
  }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (this.active && samples) {
      const copy = new Float32Array(samples);
      this.port.postMessage({ type: 'samples', samples: copy }, [copy.buffer]);
    }
    return true;
  }
}
registerProcessor('gaadi-recorder', GaadiRecorder);
