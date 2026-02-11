/* ===== HOME: mais vida ===== */
.home-hero{
  position: relative;
  border-radius: 22px;
  padding: 18px 18px 16px 18px;
  background:
    radial-gradient(420px 140px at 18% 30%, rgba(88,166,255,.22), transparent 60%),
    radial-gradient(520px 200px at 90% 20%, rgba(167,139,250,.18), transparent 60%),
    linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
  border: 1px solid rgba(255,255,255,.10);
  box-shadow:
    0 26px 70px rgba(0,0,0,.55),
    inset 0 1px 0 rgba(255,255,255,.06);
  overflow: hidden;
}

.home-hero:after{
  content:"";
  position:absolute;
  inset:-1px;
  border-radius: 22px;
  padding:1px;
  background: linear-gradient(135deg, rgba(88,166,255,.28), rgba(167,139,250,.18), rgba(0,212,255,.14));
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events:none;
  opacity:.70;
}

.home-title{
  font-size: 3.0rem;
  font-weight: 950;
  line-height: 1.05;
  color: rgba(255,255,255,.96);
  letter-spacing: .3px;
}

.home-sub{
  margin-top: 10px;
  font-weight: 800;
  color: rgba(232,237,246,.78);
}

.pill{
  display: inline-block;
  margin-left: 10px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.12);
  color: rgba(232,237,246,.86);
  font-weight: 850;
  font-size: .85rem;
}

.action-tile{
  border-radius: 16px;
  padding: 14px 14px 12px 14px;
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
  border: 1px solid rgba(55,214,122,.20);
  box-shadow: 0 16px 34px rgba(0,0,0,.40), inset 0 1px 0 rgba(255,255,255,.05);
  margin-bottom: 10px;
}

.action-tile-blue{
  border-color: rgba(88,166,255,.22);
}

.action-title{
  font-weight: 950;
  font-size: 1.05rem;
  color: rgba(232,237,246,.95);
}

.action-desc{
  margin-top: 6px;
  font-weight: 700;
  color: rgba(232,237,246,.68);
  font-size: .90rem;
}
