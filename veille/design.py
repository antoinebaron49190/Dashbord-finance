"""Systeme de design de la page : jetons, feuille de style, script, icones.

Separe de build_site.py a dessein. Le rendu et la mise en forme sont deux
metiers differents : build_site decide QUOI montrer, ce module decide a quoi
cela ressemble. Chacun se relit sans faire defiler l'autre.

Trois regles tiennent tout le reste :

  1. La couleur ne porte jamais seule une information. Le bleu est l'accent
     de l'interface, le vert ne sert qu'aux donnees favorables, le rouge
     qu'aux alertes. Tout le reste est neutre, et chaque etat est double
     d'un mot.
  2. Aucune ressource externe. Pas de police distante, pas de bibliotheque
     d'icones, pas de feuille de style tierce : la page s'ouvre entiere sans
     une seule requete reseau, y compris hors ligne.
  3. Les animations ne portent que `opacity` et `transform`, les deux seules
     proprietes que le navigateur compose sans recalculer la mise en page.
     C'est ce qui les tient a 60 images par seconde, et
     `prefers-reduced-motion` les desactive entierement.
"""

# --- Jetons -----------------------------------------------------------------
# Bleu nuit tres sombre, surfaces etagees par transparence plutot que par
# couleurs figees : les cartes restent coherentes quel que soit le fond.

TOKENS = {
    "bg": "#080B12",
    "bg_soft": "#0B0F18",
    "surface": "rgba(255,255,255,.030)",
    "surface_hi": "rgba(255,255,255,.052)",
    "line": "rgba(255,255,255,.075)",
    "line_soft": "rgba(255,255,255,.045)",
    "text": "#EAEEF6",
    "dim": "#A6B0C2",
    "faint": "#79839A",
    "accent": "#4C8DFF",
    "accent_soft": "rgba(76,141,255,.14)",
    "positive": "#3ED598",
    "negative": "#FF6B6B",
}

# Couleur d'accent par region. Elle distingue les regions entre elles, jamais
# un etat de marche : celui-ci est toujours ecrit en toutes lettres.
REGION_ACCENTS = {
    "amerique": "#4C8DFF",
    "europe": "#9B8CFF",
    "asie": "#F2B25C",
    "crypto": "#3ED598",
}

# Couleur par categorie d'article, pour la pastille de rubrique.
CATEGORY_STYLE = {
    "politique_monetaire": ("Politique monétaire", "#4C8DFF"),
    "statistiques": ("Statistiques", "#5FD3E8"),
    "reglementation": ("Réglementation", "#9B8CFF"),
    "marche": ("Marché", "#A6B0C2"),
    "crypto": ("Crypto", "#3ED598"),
}


# --- Icones -----------------------------------------------------------------
# Un seul jeu, dessine sur la meme grille de 24, meme graisse (1.75), memes
# extremites arrondies. Melanger deux jeux d'icones se voit immediatement et
# c'est le detail qui fait basculer une interface du cote « bricole ».

ICONS = {
    "trend_up": "M3 17l6-6 4 4 8-8M21 7h-5m5 0v5",
    "trend_down": "M3 7l6 6 4-4 8 8M21 17h-5m5 0v-5",
    "trend_flat": "M3 12h18",
    "search": "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35",
    "star": ("M12 3.5l2.6 5.3 5.9.9-4.25 4.15 1 5.85L12 16.95"
             "l-5.25 2.75 1-5.85L3.5 9.7l5.9-.9L12 3.5z"),
    "clock": "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3.5 2",
    "external": "M14 4h6v6M20 4l-8.5 8.5M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5",
    "calendar": "M7 3v3m10-3v3M4 9h16M5 6h14a1 1 0 011 1v12a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1z",
    "pulse": "M3 12h4l3-8 4 16 3-8h4",
    "globe": ("M12 21a9 9 0 100-18 9 9 0 000 18zM3.5 9h17M3.5 15h17"
              "M12 3c-5 6-5 12 0 18 5-6 5-12 0-18z"),
    "spark": "M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4L12 3z",
    "layers": "M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5",
    "shield": "M12 3l8 3v6c0 5-3.4 8.4-8 9-4.6-.6-8-4-8-9V6l8-3z",
    "gauge": "M12 20a8 8 0 100-16 8 8 0 000 16zM12 12l4-3",
}


def icon(name, size=18, extra=""):
    """Une icone SVG en ligne, sans dependance ni requete."""
    path = ICONS.get(name)
    if not path:
        return ""
    classes = f'icon {extra}'.strip()
    return (f'<svg class="{classes}" width="{size}" height="{size}" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.75" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true"><path d="{path}"/></svg>')


# --- Feuille de style -------------------------------------------------------

CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation-duration:.001ms!important;
    animation-iteration-count:1!important;transition-duration:.001ms!important}
}

body{margin:0;background:__BG__;color:__TEXT__;font-size:16px;line-height:1.55;
 letter-spacing:-.006em;font-family:-apple-system,BlinkMacSystemFont,
 "SF Pro Text","Inter","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
 overflow-x:hidden;
 background-image:
   radial-gradient(1200px 620px at 12% -12%, rgba(76,141,255,.10), transparent 62%),
   radial-gradient(1000px 520px at 92% -6%, rgba(155,140,255,.07), transparent 60%)}

.shell{max-width:1160px;margin:0 auto;
 padding:0 20px calc(96px + env(safe-area-inset-bottom))}
.icon{flex:0 0 auto;display:block}

/* --- Barre superieure --- */
.topbar{position:sticky;top:0;z-index:40;
 background:rgba(8,11,18,.72);backdrop-filter:saturate(150%) blur(18px);
 -webkit-backdrop-filter:saturate(150%) blur(18px);
 border-bottom:1px solid __LINE_SOFT__}
.topbar-in{max-width:1160px;margin:0 auto;padding:13px 20px;
 display:flex;align-items:center;gap:12px}
.brand{display:flex;align-items:center;gap:10px;min-width:0}
.brand-mark{width:30px;height:30px;border-radius:9px;flex:0 0 auto;
 display:grid;place-items:center;color:__ACCENT__;
 background:__ACCENT_SOFT__;border:1px solid rgba(76,141,255,.28)}
.brand-name{font-size:16px;font-weight:650;letter-spacing:-.02em;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.live{margin-left:auto;display:flex;align-items:center;gap:7px;
 font-size:14px;color:__FAINT__;font-variant-numeric:tabular-nums;
 white-space:nowrap}
.live-dot{width:7px;height:7px;border-radius:50%;background:__POSITIVE__;
 box-shadow:0 0 0 0 rgba(62,213,152,.5);animation:pulse 2.8s ease-out infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(62,213,152,.45)}
 70%{box-shadow:0 0 0 7px rgba(62,213,152,0)}
 100%{box-shadow:0 0 0 0 rgba(62,213,152,0)}}

/* --- Titres --- */
.eyebrow{display:flex;align-items:center;gap:9px;margin:0 0 15px;
 font-size:14px;font-weight:650;color:__FAINT__;text-transform:uppercase;
 letter-spacing:.13em}
.eyebrow .icon{color:__FAINT__}
h1{margin:0;font-size:clamp(32px,7vw,46px);line-height:1.04;font-weight:700;
 letter-spacing:-.038em}
h2{margin:0;font-size:19px;font-weight:650;letter-spacing:-.022em}
h3{margin:0;font-size:16px;font-weight:650;letter-spacing:-.015em}

/* --- Hero --- */
.hero{padding:46px 0 12px}
.hero-lede{margin:16px 0 0;max-width:52ch;font-size:clamp(17px,2.4vw,19px);
 line-height:1.55;color:__DIM__}
.hero-lede b{color:__TEXT__;font-weight:650}
.tiles{display:grid;gap:12px;margin:28px 0 8px;
 grid-template-columns:repeat(auto-fit,minmax(154px,1fr))}
.tile{position:relative;padding:16px 17px;border-radius:16px;
 background:__SURFACE__;border:1px solid __LINE__;
 backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
 box-shadow:0 1px 0 rgba(255,255,255,.04) inset,0 10px 26px rgba(0,0,0,.30)}
.tile-label{display:flex;align-items:center;gap:7px;font-size:14px;
 color:__FAINT__;font-weight:550;line-height:1.3;min-height:20px}
.tile-label span{min-width:0}
.tile-value{margin-top:9px;font-size:27px;font-weight:700;letter-spacing:-.03em;
 font-variant-numeric:tabular-nums;line-height:1.1}
.tile-note{margin-top:4px;font-size:14px;color:__DIM__}

/* --- Sections --- */
/* La marge d'ancrage compense la barre collante : sans elle, un lien ou un
   defilement programme depose le titre de section SOUS la barre. */
.section{margin-top:44px;scroll-margin-top:78px}
.section-head{display:flex;align-items:baseline;gap:12px;margin-bottom:16px;
 flex-wrap:wrap}
.section-head .eyebrow{margin:0}
.section-sub{font-size:14px;color:__FAINT__}

/* --- Carte generique --- */
.card{position:relative;border-radius:18px;background:__SURFACE__;
 border:1px solid __LINE__;overflow:hidden;
 backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
 box-shadow:0 1px 0 rgba(255,255,255,.04) inset,0 12px 30px rgba(0,0,0,.30);
 transition:transform .34s cubic-bezier(.22,.61,.36,1),
  border-color .34s ease,box-shadow .34s ease}
@media (hover:hover){
  .card:hover{transform:translateY(-2px);border-color:rgba(255,255,255,.13);
   box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 18px 42px rgba(0,0,0,.40)}
}

/* --- Marches --- */
.markets{display:grid;gap:14px;grid-template-columns:1fr}
.market{padding:18px 18px 16px}
.market::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;
 background:linear-gradient(90deg,var(--accent),transparent 82%)}
.market-top{display:flex;align-items:center;gap:10px}
.market-name{font-size:18px;font-weight:650;letter-spacing:-.02em}
.market-spark{margin-left:auto;opacity:.9}
.badge{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;
 border-radius:999px;font-size:14px;font-weight:600;line-height:1;
 border:1px solid transparent;white-space:nowrap}
.badge-up{color:__POSITIVE__;background:rgba(62,213,152,.11);
 border-color:rgba(62,213,152,.24)}
.badge-down{color:__NEGATIVE__;background:rgba(255,107,107,.11);
 border-color:rgba(255,107,107,.24)}
.badge-flat{color:__DIM__;background:rgba(255,255,255,.05);
 border-color:__LINE__}
.market-state{margin-top:13px}
.market-detail{margin:9px 0 0;font-size:15px;color:__DIM__;line-height:1.45}
.quotes{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
.quote{display:inline-flex;align-items:baseline;gap:7px;padding:6px 11px;
 border-radius:10px;background:rgba(255,255,255,.04);border:1px solid __LINE_SOFT__;
 font-size:14px;font-variant-numeric:tabular-nums}
.quote b{font-weight:650}
.market-foot{margin-top:14px;padding-top:12px;border-top:1px solid __LINE_SOFT__;
 font-size:14px;color:__FAINT__}

/* --- Barre d'outils du flux --- */
.toolbar{display:flex;flex-direction:column;gap:11px;margin-bottom:16px}
.search{position:relative;display:flex;align-items:center}
.search .icon{position:absolute;left:14px;color:__FAINT__;pointer-events:none}
.search input{width:100%;padding:13px 15px 13px 43px;border-radius:13px;
 background:__SURFACE__;border:1px solid __LINE__;color:__TEXT__;
 font-size:16px;font-family:inherit;outline:none;
 transition:border-color .22s ease,box-shadow .22s ease}
.search input::placeholder{color:__FAINT__}
.search input:focus{border-color:rgba(76,141,255,.55);
 box-shadow:0 0 0 4px rgba(76,141,255,.14)}
.chips{display:flex;gap:8px;overflow-x:auto;padding-bottom:3px;
 scrollbar-width:none;-ms-overflow-style:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:0 0 auto;min-height:38px;display:inline-flex;align-items:center;
 gap:7px;padding:8px 14px;border-radius:999px;background:rgba(255,255,255,.04);
 border:1px solid __LINE__;color:__DIM__;font-size:14px;font-weight:600;
 font-family:inherit;cursor:pointer;white-space:nowrap;
 transition:background .22s ease,color .22s ease,border-color .22s ease,
  transform .18s ease}
.chip:hover{color:__TEXT__;border-color:rgba(255,255,255,.16)}
.chip:active{transform:scale(.97)}
.chip[aria-pressed="true"]{background:__ACCENT_SOFT__;color:#CFE0FF;
 border-color:rgba(76,141,255,.42)}
.chip .icon{width:15px;height:15px}
.chip-count{opacity:.62;font-variant-numeric:tabular-nums}

/* --- Flux --- */
.feed{display:grid;gap:12px;grid-template-columns:1fr}
.story{position:relative;display:block;padding:17px 18px;
 text-decoration:none;color:inherit}
.story::before{content:"";position:absolute;left:0;top:16px;bottom:16px;
 width:2px;border-radius:0 2px 2px 0;background:var(--cat,#A6B0C2);opacity:.75}
.story-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
 margin-bottom:10px}
.tag{display:inline-flex;align-items:center;gap:6px;padding:4px 9px;
 border-radius:8px;font-size:14px;font-weight:600;line-height:1.25;
 background:rgba(255,255,255,.05);border:1px solid __LINE_SOFT__;color:__DIM__}
.tag-cat{color:var(--cat);border-color:color-mix(in srgb,var(--cat) 30%,transparent);
 background:color-mix(in srgb,var(--cat) 12%,transparent)}
.tag-high{color:__NEGATIVE__;border-color:rgba(255,107,107,.28);
 background:rgba(255,107,107,.10)}
.story-title{margin:0;font-size:17px;line-height:1.38;font-weight:600;
 letter-spacing:-.016em;overflow-wrap:anywhere}
.story-excerpt{margin:8px 0 0;font-size:15px;line-height:1.5;color:__DIM__;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
 overflow:hidden}
.story-foot{display:flex;align-items:center;gap:9px;margin-top:13px;
 font-size:14px;color:__FAINT__;flex-wrap:wrap}
.story-src{font-weight:600;color:__DIM__}
.dotsep{opacity:.45}
.story-actions{margin-left:auto;display:flex;align-items:center;gap:4px}
.act{width:38px;height:38px;display:grid;place-items:center;border-radius:10px;
 background:transparent;border:1px solid transparent;color:__FAINT__;
 cursor:pointer;transition:background .2s ease,color .2s ease,transform .18s ease}
.act:hover{background:rgba(255,255,255,.06);color:__TEXT__}
.act:active{transform:scale(.92)}
.act[aria-pressed="true"]{color:__ACCENT__;background:__ACCENT_SOFT__}
.act[aria-pressed="true"] .icon{fill:currentColor}
.empty{padding:34px 22px;text-align:center;color:__FAINT__;font-size:15px}
.empty strong{display:block;margin-bottom:6px;color:__DIM__;font-size:16px}

/* --- Agenda --- */
.timeline{list-style:none;margin:0;padding:0}
.tl{position:relative;display:flex;gap:15px;padding:15px 18px;
 border-bottom:1px solid __LINE_SOFT__}
.tl:last-child{border-bottom:0}
.tl-mark{flex:0 0 auto;width:9px;height:9px;border-radius:50%;margin-top:7px;
 background:__DIM__}
.tl.soon .tl-mark{background:__NEGATIVE__;
 box-shadow:0 0 0 4px rgba(255,107,107,.14)}
.tl-body{min-width:0;flex:1}
.tl-when{font-size:14px;font-weight:650;color:__DIM__}
.tl.soon .tl-when{color:__NEGATIVE__}
.tl-label{display:block;margin-top:3px;font-size:16px;line-height:1.38;
 overflow-wrap:anywhere}
.tl-date{display:block;margin-top:3px;font-size:14px;color:__FAINT__}

/* --- Analyses --- */
.grid{display:grid;gap:14px;grid-template-columns:1fr}
.panel{padding:18px}
.panel-head{display:flex;align-items:center;gap:9px;margin-bottom:4px}
.panel-head .icon{color:__ACCENT__}
.panel-sub{margin:0 0 14px;font-size:14px;color:__FAINT__;line-height:1.45}
.rows{list-style:none;margin:0;padding:0}
.row{padding:12px 0;border-bottom:1px solid __LINE_SOFT__}
.row:last-child{border-bottom:0}
.row-top{display:flex;align-items:baseline;gap:12px;justify-content:space-between}
.row-name{font-size:16px;line-height:1.3;overflow-wrap:anywhere}
.row-value{flex:0 0 auto;font-size:17px;font-weight:700;
 font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.row-line{display:block;margin-top:4px;font-size:14px;line-height:1.5;
 color:__FAINT__}
.row-flat{display:flex;align-items:baseline;gap:11px;padding:11px 0}
.row-flat .row-name{flex:0 0 92px}
.row-word{flex:1;font-size:15px}
.note{margin:13px 0 0;font-size:14px;line-height:1.5;color:__FAINT__}
.note code{font-size:14px;background:rgba(255,255,255,.06);border-radius:5px;
 padding:1px 6px;overflow-wrap:anywhere}
.points{list-style:none;counter-reset:p;margin:0;padding:0}
.point{counter-increment:p;position:relative;padding:12px 0 12px 40px;
 font-size:16px;line-height:1.5;border-bottom:1px solid __LINE_SOFT__}
.point:last-child{border-bottom:0}
.point::before{content:counter(p);position:absolute;left:0;top:12px;
 width:24px;height:24px;border-radius:8px;background:__ACCENT_SOFT__;
 color:#CFE0FF;font-size:14px;font-weight:700;line-height:23px;
 text-align:center}

/* --- Bandeau permanent --- */
.disclaimer{position:fixed;left:0;right:0;bottom:0;z-index:50;
 background:rgba(8,11,18,.86);backdrop-filter:saturate(150%) blur(16px);
 -webkit-backdrop-filter:saturate(150%) blur(16px);
 border-top:1px solid __LINE_SOFT__;color:__FAINT__;font-size:14px;
 line-height:1.4;text-align:center;
 padding:11px 20px calc(11px + env(safe-area-inset-bottom))}

/* --- Apparition progressive --- */
.reveal{opacity:0;transform:translateY(12px);
 transition:opacity .55s cubic-bezier(.22,.61,.36,1),
  transform .55s cubic-bezier(.22,.61,.36,1)}
.reveal.in{opacity:1;transform:none}
@media (prefers-reduced-motion: reduce){.reveal{opacity:1;transform:none}}

/* --- Focus visible : la navigation clavier doit rester evidente --- */
a:focus-visible,button:focus-visible,input:focus-visible{
 outline:2px solid __ACCENT__;outline-offset:3px;border-radius:10px}

/* --- Grands ecrans --- */
@media (min-width:720px){
  .shell{padding-left:32px;padding-right:32px}
  .hero{padding-top:60px}
  .markets{grid-template-columns:repeat(2,1fr)}
  .grid{grid-template-columns:repeat(2,1fr)}
  .toolbar{flex-direction:row;align-items:center}
  .search{flex:1 1 320px}
  .chips{flex:1 1 auto;justify-content:flex-end}
}
@media (min-width:1080px){
  .markets{grid-template-columns:repeat(4,1fr)}
  .feed{grid-template-columns:repeat(2,1fr)}
  .grid{grid-template-columns:repeat(3,1fr)}
  .feed-wide{grid-column:1/-1}
}
"""


def stylesheet():
    css = CSS
    mapping = {
        "__BG__": TOKENS["bg"], "__SURFACE__": TOKENS["surface"],
        "__LINE__": TOKENS["line"], "__LINE_SOFT__": TOKENS["line_soft"],
        "__TEXT__": TOKENS["text"], "__DIM__": TOKENS["dim"],
        "__FAINT__": TOKENS["faint"], "__ACCENT__": TOKENS["accent"],
        "__ACCENT_SOFT__": TOKENS["accent_soft"],
        "__POSITIVE__": TOKENS["positive"], "__NEGATIVE__": TOKENS["negative"],
    }
    for token, value in mapping.items():
        css = css.replace(token, value)
    return css


# --- Script -----------------------------------------------------------------
# Vanille, sans dependance. Il ne fabrique aucune donnee : tout est deja dans
# le HTML, il ne fait que filtrer, trier et retenir des preferences locales.

SCRIPT = """
(function(){
  var root=document.getElementById('feed');
  if(!root) return;
  var cards=[].slice.call(root.querySelectorAll('[data-story]'));
  var search=document.getElementById('q');
  var chips=[].slice.call(document.querySelectorAll('[data-filter]'));
  var count=document.getElementById('feed-count');
  var empty=document.getElementById('feed-empty');
  var filter='tout';

  // Les preferences vivent dans le navigateur : le depot est public, rien
  // de personnel ne doit en sortir. Un stockage indisponible (navigation
  // privee) ne doit pas casser la page, d'ou les try/catch.
  function read(key){
    try{ return JSON.parse(localStorage.getItem(key)||'[]'); }catch(e){ return []; }
  }
  function write(key,list){
    try{ localStorage.setItem(key,JSON.stringify(list)); }catch(e){}
  }
  var favs=read('veille.fav'), later=read('veille.later');

  function paint(){
    cards.forEach(function(card){
      var id=card.getAttribute('data-id');
      card.querySelectorAll('[data-act]').forEach(function(btn){
        var kind=btn.getAttribute('data-act');
        var on=(kind==='fav'?favs:later).indexOf(id)>=0;
        btn.setAttribute('aria-pressed',on?'true':'false');
      });
    });
  }

  function apply(){
    var q=(search&&search.value||'').trim().toLowerCase();
    var shown=0;
    cards.forEach(function(card){
      var id=card.getAttribute('data-id');
      var ok=true;
      if(filter==='fav') ok=favs.indexOf(id)>=0;
      else if(filter==='later') ok=later.indexOf(id)>=0;
      else if(filter!=='tout') ok=card.getAttribute('data-zones').indexOf(filter)>=0;
      if(ok&&q) ok=card.getAttribute('data-search').indexOf(q)>=0;
      card.hidden=!ok;
      if(ok) shown++;
    });
    if(count) count.textContent=shown;
    if(empty) empty.hidden=shown>0;
  }

  if(search) search.addEventListener('input',apply);
  chips.forEach(function(chip){
    chip.addEventListener('click',function(){
      filter=chip.getAttribute('data-filter');
      chips.forEach(function(other){
        other.setAttribute('aria-pressed',other===chip?'true':'false');
      });
      apply();
    });
  });

  root.addEventListener('click',function(event){
    var btn=event.target.closest('[data-act]');
    if(!btn) return;
    event.preventDefault();
    var card=btn.closest('[data-story]');
    var id=card.getAttribute('data-id');
    var kind=btn.getAttribute('data-act');
    var list=kind==='fav'?favs:later;
    var at=list.indexOf(id);
    if(at>=0) list.splice(at,1); else list.push(id);
    write(kind==='fav'?'veille.fav':'veille.later',list);
    paint(); apply();
  });

  paint(); apply();
})();

(function(){
  // Apparition progressive. Sans IntersectionObserver — ou si l'utilisateur
  // a demande moins d'animations — tout s'affiche immediatement : l'effet
  // est un bonus, jamais une condition pour voir le contenu.
  var items=[].slice.call(document.querySelectorAll('.reveal'));
  var calm=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(calm||!('IntersectionObserver' in window)){
    items.forEach(function(el){ el.classList.add('in'); });
    return;
  }
  var seen=new IntersectionObserver(function(entries){
    entries.forEach(function(entry){
      if(!entry.isIntersecting) return;
      entry.target.classList.add('in');
      seen.unobserve(entry.target);
    });
  },{rootMargin:'0px 0px -8% 0px',threshold:.05});
  items.forEach(function(el,i){
    el.style.transitionDelay=Math.min(i,6)*45+'ms';
    seen.observe(el);
  });
})();
"""
