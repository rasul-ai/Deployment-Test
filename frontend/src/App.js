import React, { useState, useRef, useEffect } from 'react';
import RecordRTC from 'recordrtc'; // New library
import { FaMicrophone, FaStop, FaCheck, FaExclamationTriangle, FaUpload } from 'react-icons/fa';
import './App.css'; // Optional styling

// Custom Hook using RecordRTC
function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [recorder, setRecorder] = useState(null);
  const [audioBlob, setAudioBlob] = useState(null); // Direct blob from library
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [audioDevices, setAudioDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState('default');
  const startTimeRef = useRef(null);
  const intervalRef = useRef(null);
  const streamRef = useRef(null);

  // Enumerate audio devices
  const enumerateAudioDevices = async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devices.filter(device => device.kind === 'audioinput');
      console.log('Available audio devices:', audioInputs.map(d => ({ label: d.label, deviceId: d.deviceId.substring(0, 10) + '...' })));
      setAudioDevices(audioInputs);
      if (audioInputs.length > 0) {
        setSelectedDeviceId(audioInputs[0].deviceId);
      }
    } catch (err) {
      console.error('Device enum error:', err);
    }
  };

  useEffect(() => {
    if (isRecording) {
      startTimeRef.current = Date.now();
      intervalRef.current = setInterval(() => {
        if (startTimeRef.current) {
          setRecordingDuration(Math.floor((Date.now() - startTimeRef.current) / 1000));
        }
      }, 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (startTimeRef.current) {
        const totalDuration = Math.floor((Date.now() - startTimeRef.current) / 1000);
        setRecordingDuration(totalDuration);
      }
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isRecording]);

  const startRecording = async () => {
    try {
      console.log('Starting RecordRTC with device:', selectedDeviceId);
      const constraints = {
        audio: {
          deviceId: selectedDeviceId === 'default' ? true : { exact: selectedDeviceId },
          echoCancellation: true, // Reduce noise
          noiseSuppression: true,
          sampleRate: 44100
        }
      };
      const userStream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = userStream;
      console.log('Stream obtained, active tracks:', userStream.getAudioTracks().length);

      const recordRTCInstance = new RecordRTC(userStream, {
        type: 'audio',
        mimeType: 'audio/webm',
        recorderType: RecordRTC.StereoAudioRecorder, // Reliable for audio
        timeSlice: 1000, // Chunk every 1s
        numberOfAudioChannels: 1, // Mono for Whisper
        desiredSampRate: 16000, // Optimize for Whisper
        bufferSize: 4096
      });

      recordRTCInstance.startRecording();
      setRecorder(recordRTCInstance);
      setIsRecording(true);
      setRecordingDuration(0);
      setAudioBlob(null); // Reset blob on new recording start
    } catch (err) {
      console.error('Start error:', err);
      throw new Error('Microphone access failed: ' + err.message);
    }
  };

  const stopRecording = () => {
    if (recorder && isRecording) {
      console.log('Stopping RecordRTC...');
      recorder.stopRecording(() => {
        const blob = recorder.getBlob();
        console.log('RecordRTC stopped, blob:', { size: blob.size, type: blob.type });
        setAudioBlob(blob);
        setRecorder(null);
        setIsRecording(false);
        // Stop stream
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
          streamRef.current = null;
        }
      });
    }
  };

  useEffect(() => {
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
    };
  }, []);

  return { isRecording, startRecording, stopRecording, recordingDuration, audioDevices, selectedDeviceId, setSelectedDeviceId, enumerateAudioDevices, audioBlob };
}

function App() {
  const { isRecording, startRecording, stopRecording, recordingDuration, audioDevices, selectedDeviceId, setSelectedDeviceId, enumerateAudioDevices, audioBlob } = useAudioRecorder();
  const [responseJson, setResponseJson] = useState(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [permissionGranted, setPermissionGranted] = useState(false);
  const [blobKey, setBlobKey] = useState(0); // New: Force re-mount on new blob

  // Toggle recording
  const toggleRecording = async () => {
    if (isRecording) {
      stopRecording();
      // No timeout needed - blob set in callback, useEffect handles URL
    } else {
      try {
        if (!permissionGranted) {
          await navigator.mediaDevices.getUserMedia({ audio: true });
          setPermissionGranted(true);
          await enumerateAudioDevices();
          return;
        }
        setError(null);
        setPreviewUrl(null);
        setBlobKey(prev => prev + 1); // Increment key for reset
        await startRecording();
      } catch (err) {
        setError(err.message);
      }
    }
  };

  // Auto-create preview URL when audioBlob changes
  useEffect(() => {
    if (audioBlob && audioBlob.size > 0) {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl); // Revoke old
      }
      const url = URL.createObjectURL(audioBlob);
      setPreviewUrl(url);
      setError(null);
      console.log('New preview URL created for blob size:', audioBlob.size);
    } else if (audioBlob) {
      setError(`No audio captured. Duration: ${recordingDuration}s. Blob size: ${audioBlob ? audioBlob.size : 0}. Check console.`);
    }
  }, [audioBlob]); // Watch for blob changes

  // Upload
  const uploadAudio = async () => {
    if (!audioBlob || audioBlob.size === 0) {
      setError('No audio to upload—re-record.');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('audio_file', audioBlob, 'recording.webm');

      console.log('Uploading blob size:', audioBlob.size);
      const response = await fetch('http://localhost:8000/process-referral', {
        method: 'POST',
        body: formData,
      });

      console.log('Response status:', response.status, 'OK?', response.ok);
      const responseText = await response.text();
      console.log('Raw response text:', responseText);

      if (!response.ok) {
        throw new Error(`Backend error: ${response.status} - ${responseText}`);
      }

      let jsonData;
      try {
        jsonData = JSON.parse(responseText);
        console.log('Parsed JSON:', jsonData);
      } catch (parseErr) {
        console.error('JSON parse error:', parseErr);
        throw new Error('Invalid JSON from backend: ' + responseText.substring(0, 200));
      }

      setResponseJson(jsonData);
      console.log('Set responseJson:', jsonData);
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
    } catch (err) {
      setError(err.message);
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
    }
  };

  // Reset
  const startNewRecording = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setResponseJson(null);
    setError(null);
    setPreviewUrl(null);
    setBlobKey(prev => prev + 1); // Reset key
  };

  // Debug render log
  useEffect(() => {
    if (responseJson) {
      console.log('Rendering responseJson:', responseJson);
    }
  }, [responseJson]);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Patient Referral Audio Processor</h1>
        <p>Speak patient details into the mic, then submit for extraction.</p>

        {/* Mic Button */}
        <div className="mic-container">
          <button
            onClick={toggleRecording}
            disabled={uploading}
            className={`mic-button ${isRecording ? 'recording' : ''}`}
          >
            {isRecording ? (
              <>
                <FaStop size={48} color="red" />
                <span>Stop ({recordingDuration}s)</span>
              </>
            ) : (
              <>
                <FaMicrophone size={48} color="green" />
                <span>{permissionGranted ? 'Start Recording' : 'Grant Mic Permission'}</span>
              </>
            )}
          </button>
        </div>

        {/* Device Selection */}
        {permissionGranted && !isRecording && audioDevices.length > 0 && (
          <div className="device-selection">
            <label>Select Mic: </label>
            <select value={selectedDeviceId} onChange={(e) => setSelectedDeviceId(e.target.value)}>
              {audioDevices.map((device, index) => (
                <option key={index} value={device.deviceId}>
                  {device.label || `Mic ${index + 1}`}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Preview */}
        {audioBlob && previewUrl && !responseJson && audioBlob.size > 0 && (
          <div className="preview-section">
            <h3>Preview (Duration: {recordingDuration}s, Size: {audioBlob.size} bytes):</h3>
            <audio key={blobKey} src={previewUrl} controls style={{ width: '100%', maxWidth: '300px' }} />
            <div className="preview-actions">
              <button onClick={uploadAudio} disabled={uploading} className="upload-btn">
                <FaUpload /> {uploading ? 'Uploading...' : 'Upload'}
              </button>
              <button onClick={startNewRecording} className="clear-btn">Re-Record</button>
            </div>
          </div>
        )}

        {/* Status & Errors */}
        {uploading && <div className="status">Processing audio...</div>}
        {error && (
          <div className="error">
            <FaExclamationTriangle /> {error}
            <button onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}

        {/* JSON Response */}
        {responseJson && Object.keys(responseJson).length > 0 && (
          <div className="response-card">
            <button onClick={startNewRecording} className="clear-btn">
              <FaCheck /> New Recording
            </button>
            <h2>Extracted Patient Info:</h2>
            <pre>{JSON.stringify(responseJson, null, 2)}</pre>
          </div>
        )}

        {/* Instructions */}
        {!responseJson && !isRecording && !audioBlob && !error && (
          <div className="instructions">
            <p><strong>Example:</strong> "Patient John Doe, male, age 45, symptoms: headache and fever. Refer to City Hospital."</p>
            <p><em>Speak loudly for 5-10s. Check F12 Console.</em></p>
          </div>
        )}
      </header>
    </div>
  );
}

export default App;