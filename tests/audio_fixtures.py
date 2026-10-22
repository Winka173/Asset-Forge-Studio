"""Actual original technical WAVs. Never imported into the user's Library."""
import array
import math
import wave
from pathlib import Path

def create(folder,root):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);rate=24000
    def write(name,duration,signal):
        path=folder/(name+'.wav');samples=array.array('h')
        for i in range(round(rate*duration)):
            t=i/rate;value=signal(t);samples.append(round(32767*max(-.9,min(.9,value))))
        with wave.open(str(path),'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(samples.tobytes())
        return path
    files={'music':write('original_technical_chords',8,lambda t:sum(.08*math.sin(2*math.pi*f*t) for f in ((130.81,164.81,196) if t<4 else (110,130.81,164.81)))*min(1,t/.1,(8-t)/.2))}
    for i in range(5):files['sfx'+str(i)]=write('original_technical_impact_'+str(i),.35,lambda t,i=i:.3*math.exp(-t*(12+i*2))*math.sin(2*math.pi*(90+i*70)*t))
    files['ambience']=write('original_technical_low_drone',8,lambda t:.02*math.sin(2*math.pi*55*t))
    for key,name in (('voice1','qa_david.wav'),('voice2','qa_zira.wav')):
        path=Path(root)/'.local/fixtures/audio'/name
        if path.is_file():files[key]=path
    return files
