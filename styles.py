SHARED_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800;900&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:            #eeeaf8;
  --white:         #ffffff;
  --purple:        #7b6fd4;
  --purple-light:  #a89de8;
  --purple-dark:   #5a4fb0;
  --btn-blue:      #5b8de8;
  --btn-blue-dark: #3d6fd4;
  --btn-pink:      #e86fa0;
  --btn-pink-dark: #c9507f;
  --text-dark:     #2d2557;
  --text-mid:      #6b62a8;
  --card-shadow:   0 4px 24px rgba(91,71,180,0.13);
}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"] {
  background: var(--bg) !important;
  font-family: 'Tajawal', sans-serif !important;
  direction: rtl;
}

[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stSidebarNav"],
[data-testid="stSidebar"],
footer, #MainMenu { display: none !important; }

[data-testid="stAppViewContainer"] > section:first-child { padding-top: 0 !important; }

.main .block-container {
  max-width: 500px !important;
  width: 100% !important;
  margin: 0 auto !important;
  padding: 0 20px 60px !important;
}

.blob-bg { position:fixed; inset:0; pointer-events:none; z-index:0; overflow:hidden; }
.blob { position:absolute; border-radius:50%; filter:blur(55px); opacity:0.30; }
.blob-1 { width:clamp(160px,30vw,280px); height:clamp(160px,30vw,280px); background:#c3b8f5; top:-10%; left:-8%; }
.blob-2 { width:clamp(120px,22vw,210px); height:clamp(120px,22vw,210px); background:#f5c8e8; bottom:8%; right:-6%; }
.blob-3 { width:clamp(90px,15vw,160px);  height:clamp(90px,15vw,160px);  background:#b8f0e8; top:40%; right:-4%; opacity:0.18; }

.nq-header {
  display:flex; align-items:center; justify-content:space-between;
  padding:clamp(12px,3vw,20px) 0 clamp(10px,2vw,16px);
  position:relative; z-index:10;
}
.nq-title {
  font-size:clamp(16px,4vw,22px); font-weight:800;
  color:var(--text-dark); font-family:'Tajawal',sans-serif;
  text-align:center; flex:1;
}
.nq-avatar {
  width:clamp(32px,6vw,44px); height:clamp(32px,6vw,44px); border-radius:50%;
  background:linear-gradient(135deg,#c3b8f5,#f5c8e8);
  display:flex; align-items:center; justify-content:center;
  font-size:clamp(18px,3.5vw,24px); flex-shrink:0;
}
.nq-back {
  width:clamp(32px,6vw,44px); height:clamp(32px,6vw,44px); border-radius:50%;
  background:var(--white); display:flex; align-items:center; justify-content:center;
  box-shadow:0 2px 12px rgba(123,111,212,0.18);
  font-size:clamp(16px,3vw,22px); color:var(--purple); font-weight:900;
  cursor:pointer; flex-shrink:0;
}

.nq-instruction {
  background:var(--white); border-radius:clamp(14px,3vw,20px);
  padding:clamp(8px,2vw,12px) clamp(12px,3vw,18px);
  display:flex; align-items:center; gap:clamp(8px,2vw,12px);
  box-shadow:0 2px 14px rgba(123,111,212,0.10);
  margin-bottom:clamp(12px,3vw,18px); direction:rtl;
}
.nq-instruction-icon { font-size:clamp(18px,3.5vw,26px); flex-shrink:0; }
.nq-instruction-text {
  font-size:clamp(12px,2.5vw,15px); font-weight:500;
  color:var(--text-mid); line-height:1.5; font-family:'Tajawal',sans-serif;
}

.nq-cam-frame {
  width:100%; aspect-ratio:3/4;
  border-radius:clamp(20px,4vw,30px); overflow:hidden; position:relative;
  background:#1a1a2e; box-shadow:0 8px 40px rgba(91,71,180,0.28);
  margin-bottom:clamp(12px,3vw,18px);
}
.cc { position:absolute; width:clamp(14px,3vw,22px); height:clamp(14px,3vw,22px); border-color:rgba(255,255,255,0.45); border-style:solid; }
.cc.tl { top:clamp(8px,2vw,14px); right:clamp(8px,2vw,14px); border-width:2px 0 0 2px; border-top-left-radius:4px; }
.cc.tr { top:clamp(8px,2vw,14px); left:clamp(8px,2vw,14px);  border-width:2px 2px 0 0; border-top-right-radius:4px; }
.cc.bl { bottom:clamp(8px,2vw,14px); right:clamp(8px,2vw,14px); border-width:0 0 2px 2px; border-bottom-left-radius:4px; }
.cc.br { bottom:clamp(8px,2vw,14px); left:clamp(8px,2vw,14px);  border-width:0 2px 2px 0; border-bottom-right-radius:4px; }
.cam-dots {
  position:absolute; inset:0;
  background-image:radial-gradient(rgba(160,140,255,0.07) 1px,transparent 1px);
  background-size:clamp(18px,3vw,26px) clamp(18px,3vw,26px);
}
.guide-sq {
  position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
  width:62%; aspect-ratio:1; border-radius:clamp(14px,3vw,22px);
  border:2.5px solid rgba(200,185,255,0.9);
  animation:glow-pulse 2.2s ease-in-out infinite;
}
.guide-lbl {
  position:absolute; bottom:clamp(-26px,-4vw,-20px); left:50%; transform:translateX(-50%);
  font-size:clamp(10px,2vw,13px); font-weight:600;
  color:rgba(210,200,255,0.9); white-space:nowrap; font-family:'Tajawal',sans-serif;
}
@keyframes glow-pulse {
  0%,100% { box-shadow:0 0 0 3px rgba(160,140,255,0.18),0 0 18px 4px rgba(160,140,255,0.32),inset 0 0 18px 2px rgba(160,140,255,0.08); border-color:rgba(200,185,255,0.85); }
  50%      { box-shadow:0 0 0 5px rgba(160,140,255,0.32),0 0 32px 10px rgba(160,140,255,0.50),inset 0 0 24px 6px rgba(160,140,255,0.18); border-color:rgba(220,210,255,1); }
}
.cam-error {
  position:absolute; inset:0; background:rgba(20,18,48,0.92);
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:clamp(8px,2vw,14px); text-align:center; padding:clamp(16px,4vw,28px); border-radius:inherit;
}
.cam-error-icon { font-size:clamp(32px,7vw,52px); }
.cam-error-text {
  font-size:clamp(12px,2.5vw,15px); font-weight:600;
  color:rgba(200,185,255,0.9); font-family:'Tajawal',sans-serif; line-height:1.5;
}

.nq-controls {
  display:flex; align-items:center; justify-content:center;
  gap:clamp(20px,5vw,36px); margin-bottom:clamp(10px,2.5vw,16px);
}
.icon-btn {
  width:clamp(38px,7vw,50px); height:clamp(38px,7vw,50px); border-radius:50%;
  background:rgba(255,255,255,0.82); display:flex; align-items:center; justify-content:center;
  font-size:clamp(17px,3.5vw,24px); cursor:pointer; box-shadow:0 2px 12px rgba(123,111,212,0.13);
}
.shutter {
  width:clamp(56px,11vw,76px); height:clamp(56px,11vw,76px); border-radius:50%;
  background:var(--white); border:clamp(3px,0.6vw,5px) solid var(--purple-light);
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 4px 22px rgba(123,111,212,0.32); cursor:pointer;
}
.shutter-inner {
  width:clamp(40px,8vw,56px); height:clamp(40px,8vw,56px); border-radius:50%;
  background:linear-gradient(135deg,var(--purple),var(--purple-dark));
}

.nq-learn-btn {
  display:flex; align-items:center; justify-content:center; gap:clamp(8px,2vw,12px);
  width:100%; padding:clamp(13px,3vw,18px); border-radius:clamp(16px,3vw,24px);
  background:linear-gradient(135deg,var(--btn-blue),var(--btn-blue-dark));
  color:white; font-family:'Tajawal',sans-serif;
  font-size:clamp(15px,3vw,19px); font-weight:800;
  box-shadow:0 5px 22px rgba(91,141,232,0.42); text-align:center;
  margin-bottom:clamp(8px,2vw,12px);
}
.nq-learn-icon {
  width:clamp(22px,4vw,30px); height:clamp(22px,4vw,30px);
  background:rgba(255,255,255,0.24); border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  font-size:clamp(12px,2.5vw,17px);
}

.nq-img-card {
  width:100%; border-radius:clamp(18px,4vw,28px); overflow:hidden; position:relative;
  box-shadow:0 6px 32px rgba(91,71,180,0.18); margin-bottom:clamp(10px,2.5vw,16px);
}
.nq-img-card img { width:100%; aspect-ratio:4/3; object-fit:cover; display:block; }
.nq-img-placeholder {
  width:100%; aspect-ratio:4/3;
  background:linear-gradient(135deg,#e8e4fc,#f5e8f8);
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:clamp(6px,1.5vw,10px); color:var(--text-mid);
  font-size:clamp(12px,2.5vw,15px); font-weight:500; font-family:'Tajawal',sans-serif;
}
.nq-seg-badge {
  position:absolute; top:clamp(8px,2vw,14px); right:clamp(8px,2vw,14px);
  background:rgba(76,175,125,0.92); color:white;
  font-size:clamp(10px,2vw,13px); font-weight:700; font-family:'Tajawal',sans-serif;
  padding:clamp(4px,1vw,6px) clamp(10px,2.5vw,14px); border-radius:20px;
}

.nq-word-card {
  background:var(--white); border-radius:clamp(18px,4vw,28px); box-shadow:var(--card-shadow);
  padding:clamp(14px,3vw,22px) clamp(14px,3.5vw,22px);
  margin-bottom:clamp(10px,2.5vw,16px); position:relative; overflow:hidden; direction:rtl;
}
.nq-word-card::before {
  content:''; position:absolute; top:0; right:0;
  width:clamp(60px,12vw,90px); height:clamp(60px,12vw,90px);
  background:linear-gradient(135deg,rgba(195,184,245,0.28),transparent);
  border-radius:0 clamp(18px,4vw,28px) 0 clamp(60px,12vw,90px); pointer-events:none;
}
.word-lbl {
  font-size:clamp(11px,2vw,14px); font-weight:600; color:var(--text-mid);
  letter-spacing:0.4px; font-family:'Tajawal',sans-serif; margin-bottom:clamp(8px,2vw,12px);
}
.word-row {
  display:flex; align-items:center; justify-content:space-between;
  gap:clamp(8px,2vw,14px); margin-bottom:clamp(12px,2.5vw,18px);
}
.word-left { display:flex; align-items:center; gap:clamp(10px,2.5vw,16px); }
.word-emoji { font-size:clamp(32px,7vw,48px); line-height:1; }
.word-arabic {
  font-size:clamp(26px,6vw,40px); font-weight:900; color:var(--text-dark);
  line-height:1.1; font-family:'Tajawal',sans-serif;
}
.conf-pill {
  background:linear-gradient(135deg,#eaf7f0,#d4f0e4); color:#2e7d5a;
  font-size:clamp(11px,2vw,14px); font-weight:700; font-family:'Tajawal',sans-serif;
  padding:clamp(5px,1vw,8px) clamp(10px,2.5vw,16px); border-radius:20px; flex-shrink:0;
}

.audio-lbl {
  font-size:clamp(11px,2vw,14px); font-weight:600; color:var(--text-mid);
  margin-bottom:clamp(8px,1.5vw,10px); font-family:'Tajawal',sans-serif;
}
.audio-row { display:flex; align-items:center; gap:clamp(8px,2vw,14px); }
.play-btn {
  width:clamp(40px,8vw,56px); height:clamp(40px,8vw,56px); border-radius:50%; flex-shrink:0;
  background:linear-gradient(135deg,var(--purple),var(--purple-dark));
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 4px 18px rgba(123,111,212,0.38); color:white;
  font-size:clamp(14px,3vw,20px); cursor:pointer;
}
.audio-wave { flex:1; display:flex; align-items:center; gap:clamp(2px,0.5vw,5px); height:clamp(28px,5vw,42px); }
.wbar { flex:1; background:var(--purple-light); border-radius:3px; opacity:0.5; }
.wbar:nth-child(1){height:20%} .wbar:nth-child(2){height:50%}
.wbar:nth-child(3){height:80%} .wbar:nth-child(4){height:40%}
.wbar:nth-child(5){height:70%} .wbar:nth-child(6){height:55%}
.wbar:nth-child(7){height:30%} .wbar:nth-child(8){height:65%}
.wbar:nth-child(9){height:45%} .wbar:nth-child(10){height:25%}
.audio-time {
  font-size:clamp(11px,2vw,14px); color:var(--text-mid); font-weight:600;
  min-width:clamp(28px,5vw,40px); text-align:left;
}

.nq-spell-card {
  background:var(--white); border-radius:clamp(18px,4vw,28px); box-shadow:var(--card-shadow);
  padding:clamp(14px,3vw,22px) clamp(14px,3.5vw,22px);
  margin-bottom:clamp(10px,2.5vw,16px); position:relative; overflow:hidden; direction:rtl;
}
.nq-spell-card::before {
  content:''; position:absolute; bottom:0; left:0;
  width:clamp(60px,12vw,90px); height:clamp(60px,12vw,90px);
  background:linear-gradient(135deg,transparent,rgba(195,184,245,0.22));
  border-radius:clamp(60px,12vw,90px) 0 0 clamp(18px,4vw,28px); pointer-events:none;
}
.spell-hdr { display:flex; align-items:center; gap:clamp(6px,1.5vw,10px); margin-bottom:clamp(10px,2.5vw,14px); }
.spell-hdr-icon { font-size:clamp(16px,3vw,22px); }
.spell-hdr-lbl { font-size:clamp(12px,2.5vw,15px); font-weight:700; color:var(--text-mid); font-family:'Tajawal',sans-serif; }
.spell-bubbles { display:flex; flex-wrap:wrap; gap:clamp(6px,1.5vw,10px); flex-direction:row; justify-content:flex-end; margin-bottom:clamp(8px,2vw,12px); }
.spell-bubble {
  width:clamp(38px,8vw,52px); height:clamp(42px,9vw,56px); border-radius:clamp(10px,2.5vw,16px);
  background:linear-gradient(145deg,#ede9fc,#ddd5f8); border:1.5px solid rgba(123,111,212,0.17);
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px;
  font-size:clamp(16px,4vw,24px); font-weight:900; color:var(--purple-dark);
  box-shadow:0 3px 10px rgba(91,71,180,0.10); cursor:default; user-select:none; font-family:'Tajawal',sans-serif;
}
.ltr-num { font-size:clamp(7px,1.5vw,10px); font-weight:600; color:var(--purple-light); line-height:1; }
.spell-hint { font-size:clamp(10px,2vw,13px); font-weight:500; color:var(--text-mid); opacity:0.7; text-align:center; font-family:'Tajawal',sans-serif; }

.nq-pink-btn {
  display:flex; align-items:center; justify-content:center; gap:clamp(8px,2vw,12px);
  width:100%; padding:clamp(13px,3vw,18px); border-radius:clamp(16px,3vw,24px);
  background:linear-gradient(135deg,var(--btn-pink),var(--btn-pink-dark));
  color:white; font-family:'Tajawal',sans-serif;
  font-size:clamp(15px,3vw,19px); font-weight:800;
  box-shadow:0 5px 20px rgba(232,111,160,0.38); margin-bottom:clamp(8px,2vw,12px); text-align:center;
}
.nq-outline-btn {
  display:flex; align-items:center; justify-content:center; gap:clamp(8px,2vw,12px);
  width:100%; padding:clamp(11px,2.5vw,15px); border-radius:clamp(16px,3vw,24px);
  background:var(--white); border:1.5px solid var(--purple-light);
  color:var(--purple); font-family:'Tajawal',sans-serif;
  font-size:clamp(13px,2.5vw,16px); font-weight:700; text-align:center;
}

[data-testid="stFileUploaderDropzone"] {
  border:1.5px dashed var(--purple-light) !important;
  border-radius:16px !important; background:rgba(255,255,255,0.6) !important;
}
[data-testid="stBaseButton-primary"] {
  background:linear-gradient(135deg,var(--btn-blue),var(--btn-blue-dark)) !important;
  border:none !important; border-radius:clamp(14px,3vw,20px) !important;
  font-family:'Tajawal',sans-serif !important; font-size:clamp(14px,2.5vw,17px) !important;
  font-weight:800 !important; padding:clamp(10px,2vw,14px) !important;
}
[data-testid="stBaseButton-secondary"] {
  background:var(--white) !important; border:1.5px solid var(--purple-light) !important;
  border-radius:clamp(14px,3vw,20px) !important; color:var(--purple) !important;
  font-family:'Tajawal',sans-serif !important; font-weight:700 !important;
}
[data-testid="stImage"] img {
  border-radius:clamp(14px,3vw,22px);
  box-shadow:0 4px 20px rgba(91,71,180,0.14);
}
</style>

<div class="blob-bg">
  <div class="blob blob-1"></div>
  <div class="blob blob-2"></div>
  <div class="blob blob-3"></div>
</div>
"""
