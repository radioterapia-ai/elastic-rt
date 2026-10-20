# -*- coding: utf-8 -*-
import os
import threading
import time

import radai_elastic
import radai_menu
import radai_web

VISTAS = ("fixa", "rigida", "fundida", "xadrez_rig", "xadrez", "diferenca",
          "jacobiano", "ida_e_volta")
DEPENDEM_DO_CAMPO = ("fundida", "xadrez", "diferenca", "jacobiano",
                     "ida_e_volta")
VISTAS_EM_COR = ("jacobiano", "ida_e_volta")

JANELAS = {
    "fixa": (40, 400), "rigida": (40, 400), "fundida": (40, 400),
    "xadrez_rig": (40, 400), "xadrez": (40, 400),
    "diferenca": (150, 300), "jacobiano": (1.0, 2.0),
    "ida_e_volta": (1.0, 2.0),
}

IDA_E_VOLTA_PLENA_MM = 2.0 * radai_elastic.CONSIST_P95_MM

ROTULOS = (
    ("fixa", u"Fixa", u"a s&eacute;rie de refer&ecirc;ncia, sem tocar"),
    ("rigida", u"S&oacute; r&iacute;gida", u"a m&oacute;vel apenas transladada e girada"),
    ("fundida", u"Fundida", u"a m&oacute;vel depois da deforma&ccedil;&atilde;o"),
    ("xadrez_rig", u"Xadrez r&iacute;gido", u"o que o r&iacute;gido sozinho alcan&ccedil;ou"),
    ("xadrez", u"Xadrez el&aacute;stico", u"e o que a deforma&ccedil;&atilde;o acrescentou"),
    ("diferenca", u"Diferen&ccedil;a", u"|fixa &minus; fundida|: em HU entre "
     u"duas TC; fora disso, cada s&eacute;rie normalizada pela sua janela"),
    ("jacobiano", u"Jacobiano", u"sobre a fixa, s&oacute; onde o laudo mede: "
     u"<b>azul</b> comprime, "
     u"<b>laranja</b> expande, a anatomia sozinha preserva o volume; "
     u"<b>vermelho puro &eacute; dobra</b>"),
    ("ida_e_volta", u"Ida-e-volta", u"sobre a fixa, s&oacute; onde o laudo "
     u"mede: o ponto vai pelo campo e volta pelo inverso, e quanto mais "
     u"<b>amarelo</b>, mais longe da partida ele termina; amarelo pleno "
     u"&eacute; %g mm ou mais" % IDA_E_VOLTA_PLENA_MM),
)

TETO_DOBRAS = 4000


class SemLaudo(Exception):
    pass


def conferir_laudo(tarefa, vista):
    if vista not in DEPENDEM_DO_CAMPO:
        return True
    r = (tarefa or {}).get("r") or {}
    l = r.get("laudo")
    if not l or not l.get("veredito"):
        raise SemLaudo(
            u"A vista «%s» deriva da deformação, e o laudo dela não existe. "
            u"Uma fusão elástica sempre produz imagem convincente; o que "
            u"separa fusão de ilusão é o determinante do jacobiano, e ele "
            u"sai junto com a imagem ou nenhum dos dois sai." % vista)
    return True




def _chave_de_pasta(p):
    return os.path.normcase(os.path.normpath(str(p or "").strip()))


def indice_de_pasta(pastas, pasta):
    k = _chave_de_pasta(pasta)
    for i, p in enumerate(pastas):
        if _chave_de_pasta(p.get("pasta")) == k:
            return i + 1
    return 0


def _serie_guardada(s, fazer_bilhete):
    uid = str(s.get("uid") or "")
    return {"b": fazer_bilhete(s.get("pasta") or "", uid), "uid": uid,
            "pasta": s.get("pasta") or u"",
            "numero": s.get("numero"),
            "cortes": int(s.get("cortes") or 0),
            "esp": s.get("espessura_mm"),
            "date": s.get("date") or u"",
            "curto": s.get("curto") or uid[-8:]}


def serie_do_bilhete(pastas, b):
    b = str(b or "")
    for p in pastas or ():
        for s in p.get("series") or ():
            if s.get("b") == b:
                return s
    return None


def carregar_serie(s, ler=None):
    if ler is None:
        import engine
        ler = engine.load_sitk
    pasta = s.get("pasta") or u""
    if not pasta or not os.path.isdir(pasta):
        raise ValueError(u"Não consegui abrir a série …%s: a pasta sumiu"
                         % (s.get("curto") or str(s.get("uid") or u"")[-8:]))
    return ler(pasta, s.get("uid") or None)


def rotulo_de(s, n):
    esp = s.get("esp")
    num = s.get("numero")
    return (u"[%d] série %s · %d cortes · %s · %s · …%s"
            % (n, num if num is not None else u"?",
               int(s.get("cortes") or 0),
               (u"%.2f mm" % esp) if esp else u"esp. ?",
               s.get("date") or u"sem data", s.get("curto") or u""))


def acumular_pasta(pastas, pasta, achadas, fazer_bilhete=None):
    if fazer_bilhete is None:
        import radai_thumbnail
        fazer_bilhete = radai_thumbnail.bilhete
    pastas, avisos = list(pastas), []
    ja = indice_de_pasta(pastas, pasta)
    if ja:
        avisos.append(u"Esta pasta já está na lista, com o número [%d]. Nada "
                      u"foi acrescentado." % ja)
        return pastas, avisos

    vistos = {}
    for i, p in enumerate(pastas):
        for s in p.get("series") or ():
            vistos.setdefault(s["uid"], (i + 1, s))

    novas = []
    n = len(pastas) + 1
    for bruta in achadas:
        uid = str(bruta.get("uid") or "")
        antes = vistos.get(uid)
        if antes is None:
            s = _serie_guardada(bruta, fazer_bilhete)
            vistos[uid] = (n, s)
            novas.append(s)
            continue
        onde, velha = antes
        cortes = int(bruta.get("cortes") or 0)
        curto = bruta.get("curto") or uid[-8:]
        if cortes == velha["cortes"]:
            avisos.append(
                u"A série …%s já estava na lista, vinda da pasta [%d]. A "
                u"cópia desta pasta foi ignorada — mesmo SeriesInstanceUID é "
                u"a mesma série, e escolher «a outra» não mudaria nada."
                % (curto, onde))
            continue
        if cortes < velha["cortes"]:
            avisos.append(
                u"A série …%s aparece na pasta [%d] com %d cortes e nesta "
                u"com %d. Ficou a MAIOR, a da pasta [%d] — a cópia desta "
                u"pasta está incompleta. Se for a maior que não serve, tire "
                u"a pasta [%d] da lista." % (curto, onde, velha["cortes"],
                                             cortes, onde, onde))
            continue
        if onde == n:
            novas = [x for x in novas if x["uid"] != uid]
        else:
            pastas[onde - 1] = dict(
                pastas[onde - 1],
                series=[x for x in (pastas[onde - 1].get("series") or ())
                        if x["uid"] != uid])
        s = _serie_guardada(bruta, fazer_bilhete)
        vistos[uid] = (n, s)
        novas.append(s)
        avisos.append(
            u"A série …%s aparece na pasta [%d] com %d cortes e nesta com "
            u"%d. Ficou a MAIOR, a desta pasta — a cópia da [%d] está "
            u"incompleta." % (curto, onde, velha["cortes"], cortes, onde))
    pastas.append({"pasta": str(pasta), "series": novas})
    return pastas, avisos


def tirar_pasta(pastas, n):
    try:
        i = int(n) - 1
    except (TypeError, ValueError):
        return list(pastas), None
    if i < 0 or i >= len(pastas):
        return list(pastas), None
    nova = list(pastas)
    return nova, (nova.pop(i).get("pasta") or u"")


def para_a_tela(pastas):
    fora_p, fora_s = [], []
    for i, p in enumerate(pastas):
        n = i + 1
        series = p.get("series") or ()
        fora_p.append({"n": n, "pasta": p.get("pasta") or u"",
                       "series": len(series)})
        for s in series:
            fora_s.append({"b": s["b"], "rotulo": rotulo_de(s, n)})
    return {"pastas": fora_p, "series": fora_s}


MODALIDADES = ("CT", "MR", "PT")
MIN_CORTES = 8
TETO_PASTAS = 20000
TETO_SERIES = 500


def _inteiro(x):
    try:
        return int(float(str(x).strip()))
    except (TypeError, ValueError):
        return None


def achada_de(linha):
    uid = str(linha.get("uid") or u"")
    return {"uid": uid, "pasta": linha.get("pasta") or u"",
            "cortes": int(linha.get("cortes") or 0),
            "numero": _inteiro(linha.get("numero")),
            "espessura_mm": linha.get("espessura_mm"),
            "date": str(linha.get("data") or u""),
            "modalidade": str(linha.get("modalidade") or u""),
            "curto": uid[-8:]}


def achadas(v):
    return [achada_de(s) for s in list(v.get("series") or ())]


def nova_varredura(pasta, acumular):
    import radai_dicom
    v = radai_dicom.nova_busca()
    v.update({"v": os.urandom(8).hex(), "pasta": str(pasta),
              "acumular": bool(acumular), "fim": False, "assentada": False,
              "erro": None, "avisos": []})
    return v


def varrer_pasta(v):
    import radai_dicom
    try:
        raiz = radai_dicom.caminho_longo(v["pasta"])
        if not os.path.isdir(raiz):
            v["erro"] = PASTA_NAO_ENCONTRADA % v["pasta"]
            return
        radai_dicom.buscar_series(raiz, busca=v, modalidades=MODALIDADES,
                                  min_cortes=MIN_CORTES,
                                  teto_pastas=TETO_PASTAS,
                                  teto_series=TETO_SERIES)
    except Exception as e:
        v["erro"] = u"%s: %s" % (type(e).__name__, e)


def avisos_da_varredura(v):
    import radai_dicom
    return radai_dicom.avisos_da_busca(v)


PASTA_NAO_ENCONTRADA = u"Pasta não encontrada: %s"
SEM_ROOT = (u"A pasta dos exames ainda não foi configurada: escolha uma "
            u"pasta com «Procurar…».")
BUSCA_DESCONHECIDA = (u"Esta busca não existe mais — o programa pode ter "
                      u"sido reiniciado. Clique em «Procurar séries» de novo.")


SOMA = (u"&laquo;Procurar s&eacute;ries&raquo; substitui a lista; "
        u"&laquo;Adicionar outra pasta&raquo; soma a ela. As duas "
        u"s&eacute;ries da fus&atilde;o n&atilde;o precisam estar na mesma "
        u"pasta.")


CSS = u"""
.el-wrap{display:flex;flex-direction:column;gap:14px;padding:0 18px 24px;
 max-width:1440px;margin:0 auto;box-sizing:border-box}
.el-pastas[hidden]{display:none}
.el-topo .ui-bt{height:36px;align-self:flex-end}
.el-topo{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.el-campo{display:flex;flex-direction:column;gap:4px;min-width:210px;flex:1}
.el-campo label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;
 color:var(--txt-fraco)}
.el-campo select,.el-campo input{background:var(--fundo-2);color:var(--txt);
 border:1px solid var(--linha);border-radius:8px;padding:7px 9px;font:inherit;
 font-size:13px}
.el-bt{background:var(--mod-elastic);color:var(--bg-0);border:0;border-radius:9px;
 padding:9px 18px;font:inherit;font-weight:700;cursor:pointer}
.el-bt[disabled]{opacity:.45;cursor:default}
.el-bt2{background:transparent;color:var(--txt);border:1px solid var(--linha);
 border-radius:9px;padding:8px 14px;font:inherit;font-size:13px;cursor:pointer}
.el-aviso{border-left:3px solid var(--mod-elastic);background:var(--fundo-2);
 padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;line-height:1.6;
 color:var(--txt-fraco)}
.el-aviso b{color:var(--txt)}
.el-pastas{display:flex;flex-direction:column;gap:5px}
.el-pasta-lin{display:flex;gap:10px;align-items:center;font-size:12px;
 background:var(--fundo-2);border:1px solid var(--linha);border-radius:8px;
 padding:6px 8px 6px 11px}
.el-pasta-n{color:var(--mod-elastic);font-variant-numeric:tabular-nums;
 flex:none}
.el-pasta-cam{flex:1;min-width:0;color:var(--txt);overflow-wrap:anywhere}
.el-pasta-q{color:var(--txt-fraco);flex:none;white-space:nowrap}
.el-x{background:transparent;border:1px solid var(--linha);flex:none;
 color:var(--txt-fraco);border-radius:6px;cursor:pointer;font:inherit;
 font-size:14px;line-height:1;padding:3px 9px}
.el-x:hover{color:var(--perigo);border-color:var(--perigo)}
.el-avisos{display:none;flex-direction:column;gap:6px}
.el-aviso-lin{border-left:3px solid var(--aviso);background:var(--fundo-2);
 padding:8px 12px;border-radius:0 8px 8px 0;font-size:12.5px;line-height:1.6;
 color:var(--txt-fraco)}
.el-busca{display:flex;flex-direction:column;gap:7px}
.el-busca[hidden]{display:none}
.el-busca-barra{position:relative;height:4px;background:var(--fundo-2);
 border-radius:2px;overflow:hidden}
.el-busca-barra i{position:absolute;top:0;bottom:0;left:0;width:30%;
 border-radius:2px;background:var(--mod-elastic);transform:translateX(-100%);
 animation:el-vai 1.4s cubic-bezier(.45,0,.55,1) infinite}
@keyframes el-vai{from{transform:translateX(-100%)}to{transform:translateX(340%)}}
@media (prefers-reduced-motion:reduce){.el-busca-barra i{animation:none;
 transform:none;width:100%;opacity:.45}}
.el-busca-lin{display:flex;flex-wrap:wrap;gap:6px;align-items:center;
 font-size:12px;color:var(--txt-fraco)}
.el-busca-lin b{color:var(--txt);font-variant-numeric:tabular-nums}
.el-busca-lin .el-bt2{margin-left:auto;padding:4px 11px;font-size:12px}
.el-falha{display:flex;flex-wrap:wrap;gap:10px;align-items:center;
 border-left:3px solid var(--perigo);background:var(--fundo-2);padding:8px 12px;
 border-radius:0 8px 8px 0;font-size:13px;line-height:1.5;color:var(--txt)}
.el-falha[hidden]{display:none}
.el-falha .el-bt2{padding:4px 11px;font-size:12px}
.el-prog{display:none;flex-direction:column;gap:6px}
.el-prog.on{display:flex}
.el-barra{height:6px;background:var(--fundo-2);border-radius:3px;overflow:hidden}
.el-barra i{display:block;height:100%;width:0;background:var(--mod-elastic);
 transition:width .4s ease}
.el-fase{font-size:12px;color:var(--txt-fraco)}
.el-corpo{display:none;grid-template-columns:minmax(0,1fr) 340px;gap:16px;
 align-items:start}
.el-corpo.on{display:grid}
@media(max-width:1050px){.el-corpo.on{grid-template-columns:minmax(0,1fr)}}
.el-corpo.esperando{grid-template-columns:minmax(0,1fr)}
.el-corpo.esperando .el-laudo{display:none}
.el-corpo.esperando .el-vistas,.el-corpo.esperando .el-linha,
.el-corpo.esperando .el-legenda{visibility:hidden}
.el-corpo.esperando .el-palco{aspect-ratio:auto;height:min(52vh,520px)}
.el-vistas{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.el-vista{background:var(--fundo-2);color:var(--txt-fraco);border:1px solid
 var(--linha);border-radius:7px;padding:5px 11px;font-size:12px;cursor:pointer}
.el-vista.on{background:var(--mod-elastic-fraco);color:var(--txt);
 border-color:var(--mod-elastic)}
.el-palco{position:relative;background:var(--img-fundo,#000);border-radius:10px;overflow:hidden;
 border:1px solid var(--linha);aspect-ratio:1/1;margin:0 auto;max-width:100%}
.el-palco img{width:100%;height:100%;display:block;image-rendering:pixelated}
.el-palco img:not([src]){visibility:hidden}
.el-palco svg{position:absolute;inset:0;width:100%;height:100%}
.el-grade{fill:none;stroke:var(--mod-elastic);stroke-width:.35;opacity:.75}
.el-seta{stroke:var(--mod-elastic-b);stroke-width:.45;opacity:.9}
.el-dobra{fill:#FF4D4D;opacity:.95}
.el-legenda{font-size:11px;color:var(--txt-fraco);margin-top:7px;line-height:1.6}
.el-linha{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
.el-linha input[type=range]{flex:1;min-width:160px}
.el-chk{display:flex;gap:5px;align-items:center;font-size:12px;
 color:var(--txt-fraco);cursor:pointer;--ui-check-cor:var(--mod-elastic)}
.el-laudo{background:var(--fundo-2);border:1px solid var(--linha);
 border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:12px}
.el-vered{display:flex;gap:9px;align-items:center;font-weight:700;font-size:15px}
.el-pt{width:11px;height:11px;border-radius:50%;flex:none}
.el-v-passa .el-pt{background:var(--success)} .el-v-passa{color:var(--success)}
.el-v-atencao .el-pt{background:var(--aviso)} .el-v-atencao{color:var(--aviso)}
.el-v-reprova .el-pt{background:var(--perigo)} .el-v-reprova{color:var(--perigo)}
.el-porques{margin:0;padding-left:17px;font-size:12.5px;line-height:1.65;
 color:var(--txt-fraco)}
.el-porques li{margin-bottom:6px}
.el-tab{width:100%;border-collapse:collapse;font-size:12.5px;
 font-variant-numeric:tabular-nums}
.el-tab th{text-align:left;font-weight:600;font-size:10.5px;padding:8px 0 4px;
 letter-spacing:.09em;text-transform:uppercase;color:var(--txt-fraco);
 border-bottom:1px solid var(--linha)}
.el-tab td{padding:4px 0;border-bottom:1px solid var(--linha-fraca)}
.el-tab td:last-child{text-align:right;color:var(--txt)}
.el-tab td:first-child{color:var(--txt-fraco)}
.el-ir{background:transparent;border:0;padding:0;color:var(--mod-elastic);
 font:inherit;cursor:pointer;text-decoration:underline;
 text-underline-offset:2px}
.el-nota{font-size:11.5px;line-height:1.6;color:var(--txt-fraco);
 border-top:1px solid var(--linha);padding-top:10px}
.el-erro{color:var(--perigo);font-size:13px;line-height:1.6}
.el-cartoes{margin:0}
.el-lista{display:flex;flex-direction:column;gap:5px;max-height:40vh;overflow:auto}
.el-it{display:block;width:100%;text-align:left;padding:7px 10px;font:inherit;
 font-size:12.5px;border-radius:8px;border:1px solid var(--linha);
 background:var(--fundo-2);color:var(--txt);cursor:pointer}
.el-it:hover,.el-it[aria-selected="true"]{border-color:var(--mod-elastic)}
.el-it:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#el_escolha .el-topo,#el_escolha .el-legenda,#el_escolha .el-busca,
#el_escolha .el-pastas{margin-bottom:10px}
.el-sujeitos{display:flex;align-items:flex-start;gap:9px;padding:9px 12px;
 border:1px solid var(--borda-aviso);border-radius:var(--r-lg,8px);
 background:var(--fundo-aviso);color:var(--text);font-size:12.5px;line-height:1.5}
.el-sujeitos[hidden]{display:none}
.el-sujeitos .pt{width:7px;height:7px;border-radius:50%;flex:0 0 auto;
 margin-top:6px;background:var(--aviso)}
"""

JS = u"""
var elJ=null, elVista='xadrez', elZ=0, elNZ=1, elLaudo=null, elPronto=false;
var elFundindo=false, elFusaoRelogio=null, elFalhasFusao=0;
var elV=null, elBuscaRelogio=null, elFalhasBusca=0;
var elDeNovo=null, elAssinatura='', elParVisto='', elParPedido=0;
var EL_SEL={fixa:null, movel:null}, elLista=[], elTabela=null;
var EL_TEMPO_MS=20000, EL_TEMPO_LONGO_MS=45000, EL_FALHAS_ATE_AVISAR=3;
function elEsc(t){ return String(t==null?'':t).replace(/&/g,'&amp;')
 .replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') }
function el(id){ return document.getElementById(id) }

function elPedir(url, corpo, ms){
  var ctl = (typeof AbortController === 'function') ? new AbortController() : null;
  var opc = (corpo === undefined) ? {cache:'no-store'}
    : {method:'POST', cache:'no-store', headers:{'Content-Type':'application/json'},
       body:JSON.stringify(corpo)};
  if(ctl) opc.signal = ctl.signal;
  var relogio = null;
  var prazo = new Promise(function(_ok, falha){
    relogio = setTimeout(function(){
      if(ctl) ctl.abort();
      falha({semResposta:true});
    }, ms || EL_TEMPO_MS);
  });
  var pedido = fetch(url, opc).then(function(r){
    return r.json().catch(function(){ throw {semResposta:false, http:r.status} });
  }, function(){ throw {semResposta:true} });
  return Promise.race([pedido, prazo]).then(function(d){
    clearTimeout(relogio); return d;
  }, function(e){
    clearTimeout(relogio);
    throw (e && typeof e.semResposta === 'boolean') ? e : {semResposta:false};
  });
}

function elTexto(no, t){
  if(window.uiTexto) window.uiTexto(no, t || ''); else no.textContent = t || '';
}
function elErro(t){
  var e = el('el-erro'); if(!e) return;
  elTexto(e, t);
  if(t && window.radaiRetraduzir) window.radaiRetraduzir();
}
function elFalha(e, deNovo){
  var sem = !e || e.semResposta !== false;
  elTexto(el('el-falha-txt'), sem ? 'O app não respondeu.'
                                  : 'O app respondeu com erro.');
  el('el-falha-cod').textContent = (!sem && e && e.http) ? (' HTTP ' + e.http) : '';
  elDeNovo = deNovo || null;
  el('el-denovo').hidden = !deNovo;
  el('el-falha').hidden = false;
  if(window.radaiRetraduzir) window.radaiRetraduzir();
}
function elFalhaLimpar(){ el('el-falha').hidden = true; elDeNovo = null }
function elTentarDeNovo(){
  var f = elDeNovo; elFalhaLimpar(); if(f) f();
}

function elBuscaMostrar(sim){
  el('el-busca').hidden = !sim;
  if(sim){
    ['el-busca-pastas','el-busca-arqs','el-busca-series'].forEach(function(i){
      el(i).textContent = '0' });
  }
}
function elBuscaContar(d){
  if(d.pastas_olhadas === undefined) return;
  el('el-busca-pastas').textContent = String(d.pastas_olhadas || 0);
  el('el-busca-arqs').textContent = String(d.arquivos || 0);
  el('el-busca-series').textContent = String(d.series_achadas || 0);
}
function elTremer(id){
  var c = el(id); if(!c) return;
  var alvo = (c.closest && c.closest('.el-campo')) || c;
  if(window.uiTremer){ window.uiTremer(alvo); return }
  try{ c.scrollIntoView({block:'center'}) }catch(e){}
  try{ c.focus() }catch(e){}
}
function elVarrer(acumular){
  if(acumular && !(el('el-pasta').value || '').trim()){
    elErro('Escolha a pasta que vai entrar na lista.');
    elTremer('el-pasta');
    return;
  }
  elErro(''); elFalhaLimpar();
  if(elBuscaRelogio){ clearTimeout(elBuscaRelogio); elBuscaRelogio=null }
  elV = null; elBuscaMostrar(true);
  elPedir('/api/elastic/series', {pasta: el('el-pasta').value,
                                  acumular: acumular ? true : false})
   .then(function(d){
    if(d.v){ elV = d.v; elFalhasBusca = 0; elPintar(d, true); elBuscaSeguir(); return }
    elBuscaMostrar(false); elPintar(d, false);
   }).catch(function(e){
    elBuscaMostrar(false); elFalha(e, function(){ elVarrer(acumular) });
   });
}
function elBuscaSeguir(){
  if(elBuscaRelogio){ clearTimeout(elBuscaRelogio); elBuscaRelogio=null }
  if(!elV) return;
  var meu = elV;
  elPedir('/api/elastic/varredura?v=' + encodeURIComponent(meu)).then(function(d){
    if(meu !== elV) return;
    elFalhasBusca = 0;
    elPintar(d, !!d.buscando);
    if(d.buscando){ elBuscaRelogio = setTimeout(elBuscaSeguir, 700); return }
    elV = null; elBuscaMostrar(false);
  }).catch(function(e){
    if(meu !== elV) return;
    if(++elFalhasBusca < EL_FALHAS_ATE_AVISAR){
      elBuscaRelogio = setTimeout(elBuscaSeguir, 1500); return }
    elFalhasBusca = 0; elFalha(e, elBuscaSeguir);
  });
}
function elPararBusca(){
  if(!elV) return;
  var meu = elV;
  if(elBuscaRelogio){ clearTimeout(elBuscaRelogio); elBuscaRelogio=null }
  elPedir('/api/elastic/parar_busca', {v: meu}).then(function(d){
    if(meu !== elV) return;
    elV = null; elBuscaMostrar(false); elPintar(d, false);
  }).catch(function(e){ elFalha(e, elPararBusca) });
}

function elTirar(n){
  elErro(''); elFalhaLimpar();
  elPedir('/api/elastic/remover_pasta', {n:n}).then(function(d){ elPintar(d, !!elV) })
   .catch(function(e){ elFalha(e, function(){ elTirar(n) }) });
}

function elPintar(d, buscando){
  if(d.series){
    var ass = JSON.stringify([d.pastas || [],
      d.series.map(function(s){ return s.b + '|' + s.rotulo })]);
    if(ass !== elAssinatura){
      elAssinatura = ass;
      elPastasPintar(d.pastas || []);
      elSeriesPintar(d.series);
    }
    elAvisosPintar(d.avisos || []);
  }
  elBuscaContar(d);
  elLiberarFundir();
  if(d.erro) elErro(d.erro);
  else if(!buscando) elErro('');
  if(window.radaiRetraduzir) window.radaiRetraduzir();
}

function elB(qual){ return EL_SEL[qual] ? EL_SEL[qual].b : '' }
function elLiberarFundir(){
  el('el-fundir').disabled = !elB('fixa') || !elB('movel') || elFundindo;
}
function elPopup(){
  if(!window.uiPopupSerie) return null;
  return window.uiPopupSerie('el_escolha', {
    aoAbrir: function(qual){
      window.uiPopupSerie('el_escolha', {titulo: qual === 'fixa'
        ? @CARTAO_FIXA_JS@ : @CARTAO_MOVEL_JS@});
      elTabelaLigar(); elMarcarLista();
    }});
}
function elTabelaLigar(){
  if(elTabela || !window.uiTabelaAcervo || !el('el_acervo')) return;
  elTabela = window.uiTabelaAcervo('el_acervo', {aoAbrir: function(linha){
    if(!linha || !linha.bilhete) return;
    var d = String(linha.date || '');
    if(d.length >= 8) d = d.slice(6, 8) + '/' + d.slice(4, 6) + '/' + d.slice(0, 4);
    elEscolher(linha.bilhete, [d, linha.pid, linha.modalidade]
      .filter(function(x){ return x }).join(' · '));
  }});
}
function elEscolher(b, rotulo){
  var p = elPopup(), qual = (p && p.contexto()) || 'movel';
  if(qual !== 'fixa') qual = 'movel';
  EL_SEL[qual] = {b: b, rotulo: rotulo || ''};
  if(window.uiCartaoRotulo) window.uiCartaoRotulo('el-' + qual, rotulo || '');
  if(p) p.fechar();
  elErro(''); elLiberarFundir(); elConferirPar();
}
function elMarcarLista(){
  var p = elPopup(), qual = (p && p.contexto()) || 'movel', b = elB(qual);
  Array.prototype.forEach.call(document.querySelectorAll('#el-lista .el-it'), function(x){
    x.setAttribute('aria-selected', x.getAttribute('data-b') === b ? 'true' : 'false');
  });
}

function elConferirPar(){
  var a = elB('fixa'), b = elB('movel');
  var par = a + '|' + b;
  if(par === elParVisto) return;
  elParVisto = par;
  elConferirSujeitos(a, b);
}
function elConferirSujeitos(a, b){
  var al = el('el-sujeitos'); if(!al) return;
  var meu = ++elParPedido;
  if(!a || !b || a === b){ al.hidden = true; return }
  elPedir('/api/elastic/par', {fixa:a, movel:b}, EL_TEMPO_LONGO_MS).then(function(d){
    if(meu !== elParPedido) return;
    al.hidden = !(d && d.sujeitos_diferentes === true);
    if(!al.hidden && window.radaiRetraduzir) window.radaiRetraduzir();
  }).catch(function(){ if(meu === elParPedido) al.hidden = true });
}

function elSeriesPintar(series){
  var h=el('el-lista');
  elLista = series || [];
  h.innerHTML='';
  elLista.forEach(function(s){
    var o=document.createElement('button');
    o.type='button'; o.className='el-it'; o.setAttribute('role', 'option');
    o.setAttribute('data-b', s.b); o.setAttribute('translate', 'no');
    o.textContent=s.rotulo; h.appendChild(o);
  });
  elMarcarLista();
}

function elPastasPintar(pastas){
  var h=el('el-pastas');
  h.innerHTML='';
  pastas.forEach(function(p){
    var lin=document.createElement('div'); lin.className='el-pasta-lin';
    var num=document.createElement('b'); num.className='el-pasta-n';
    num.textContent='['+p.n+']';
    var cam=document.createElement('span'); cam.className='el-pasta-cam';
    cam.textContent=p.pasta;
    var q=document.createElement('span'); q.className='el-pasta-q';
    q.textContent=String(p.series)+' ';
    var qp=document.createElement('span');
    qp.setAttribute('data-radai-frase','');
    qp.textContent=(p.series===1?'série':'séries');
    q.appendChild(qp);
    var x=document.createElement('button'); x.className='el-x';
    x.type='button'; x.innerHTML='&times;';
    x.title='Tirar esta pasta da lista, e as séries dela junto';
    x.setAttribute('data-n', String(p.n));
    x.addEventListener('click', function(){
      elTirar(parseInt(this.getAttribute('data-n'),10)) });
    lin.appendChild(num); lin.appendChild(cam); lin.appendChild(q);
    lin.appendChild(x);
    h.appendChild(lin);
  });
}

function elProcurar(){
  if(!window.uiExplorador) return;
  window.uiExplorador({inicial:(el('el-pasta').value||'').trim(), origem:el('el-procurar'),
    aoUsar:function(c){ el('el-pasta').value=c||''; el('el-buscar').focus() }});
}

function elAvisosPintar(avisos){
  var h=el('el-avisos');
  h.innerHTML='';
  h.style.display = avisos.length ? 'flex' : 'none';
  avisos.forEach(function(t){
    var p=document.createElement('div'); p.className='el-aviso-lin';
    p.textContent=t; h.appendChild(p);
  });
}

function elEsperarVisor(sim){
  var c=el('el-corpo'), p=el('el-palco');
  if(sim){
    c.classList.add('on'); c.classList.add('esperando');
    el('el-img').removeAttribute('src'); el('el-svg').innerHTML='';
    el('el-cortou').textContent='';
    p.style.aspectRatio=''; p.style.width='';
    if(window.uiCarregando) window.uiCarregando(p, true, 'fundindo as duas séries…');
    return;
  }
  c.classList.remove('esperando');
  if(window.uiCarregando) window.uiCarregando(p, false);
}

function elFundir(){
  var a=elB('fixa'), b=elB('movel');
  if(!a||!b){ elTremer(b ? 'el-fixa' : 'el-movel'); return }
  if(a===b){
    elErro('A série fixa e a móvel são a mesma. Fundir uma série com ela mesma devolve o campo nulo — é um laudo perfeito que não mediu nada.');
    elTremer('el-movel');
    return }
  elErro(''); elFalhaLimpar();
  elFundindo=true; el('el-fundir').disabled=true;
  elJ=null; elPronto=false;
  el('el-fase').textContent=''; el('el-pct').style.width='0%';
  el('el-prog').classList.add('on');
  elEsperarVisor(true);
  elPedir('/api/elastic/fundir', {fixa:a, movel:b,
      esp:parseFloat(el('el-esp').value),
      malha:parseInt(el('el-malha').value,10),
      so_rigido: el('el-sorig').checked})
   .then(function(d){
    if(d.erro){ elParar(d.erro); return }
    elJ=d.j; elFalhasFusao=0; elPerguntar();
   }).catch(function(e){ elParar(''); elFalha(e, elFundir) });
}

function elParar(msg){
  if(elFusaoRelogio){ clearTimeout(elFusaoRelogio); elFusaoRelogio=null }
  elFundindo=false;
  el('el-prog').classList.remove('on');
  elLiberarFundir();
  if(!elPronto){ elEsperarVisor(false); el('el-corpo').classList.remove('on') }
  if(msg){ elErro(msg) }
}

function elPerguntar(){
  if(elFusaoRelogio){ clearTimeout(elFusaoRelogio); elFusaoRelogio=null }
  if(!elJ || elPronto){ return }
  var meu = elJ;
  elPedir('/api/elastic/estado?j='+encodeURIComponent(meu), undefined, EL_TEMPO_LONGO_MS)
   .then(function(d){
    if(meu !== elJ) return;
    elFalhasFusao = 0;
    el('el-fase').textContent = d.fase||'';
    el('el-pct').style.width = (d.pct||0)+'%';
    if(d.erro){ elParar(d.erro); return }
    if(!d.pronto){ elFusaoRelogio = setTimeout(elPerguntar, 1200); return }
    elPronto=true; elParar(''); elEsperarVisor(false);
    elLaudo=d.laudo; elNZ=d.nz||1; elZ=Math.floor(elNZ/2);
    var s=el('el-z'); s.max=String(elNZ-1); s.value=String(elZ);
    if(d.nx && d.ny){
      var pal = el('el-palco');
      pal.style.aspectRatio = d.nx+' / '+d.ny;
      pal.style.width = 'min(100%, calc(74vh * '
        + (d.nx/d.ny).toFixed(4) + '))';
    }
    el('el-corpo').classList.add('on');
    elDesenharLaudo(d);
    elCorte();
   }).catch(function(e){
    if(meu !== elJ) return;
    if(++elFalhasFusao < EL_FALHAS_ATE_AVISAR){
      elFusaoRelogio = setTimeout(elPerguntar, 2000); return }
    elFalhasFusao = 0; elFalha(e, elPerguntar);
   });
}

function elNum(v,d){ return (v===null||v===undefined)?'&mdash;'
  :Number(v).toFixed(d===undefined?2:d) }

function elLinhasDoAr(ar){
  var fora = [['<th colspan=2>Ar contra tecido</th>','']];
  if(!ar || !ar.aplica){
    fora.push(['onde uma série tem gás e a outra tecido', 'medido só entre duas TC']);
    return fora;
  }
  fora.push(['volume', elNum(ar.cm3,1)+' cm&sup3;']);
  fora.push(['regiões', String(ar.n||0)]);
  (ar.regioes||[]).forEach(function(g){
    var meio = Math.floor((g.corte_de + g.corte_ate) / 2);
    fora.push(['<button type="button" class="el-ir" data-z="' + (meio-1) + '">'
      + 'cortes ' + g.corte_de + '&ndash;' + g.corte_ate + '</button> &middot; '
      + (g.gas_na==='fixa' ? 'gás na fixa' : 'gás na móvel'),
      elNum(g.cm3,1)+' cm&sup3;']);
  });
  return fora;
}

function elDesenharLaudo(d){
  var l=d.laudo||{}, v=l.veredito||'atencao';
  var nomes={passa:'Transformação plausível', atencao:'Olhar antes de usar',
             reprova:'O campo DOBRA'};
  el('el-vered').className = 'el-vered el-v-'+v;
  el('el-vered').innerHTML = '<i class="el-pt"></i>'+elEsc(nomes[v]||v);
  var pqs = (l.porques||[]).slice();
  if(d.sujeitos_diferentes === true) pqs.push(@SUJEITOS_LAUDO_JS@);
  el('el-porques').innerHTML =
    pqs.map(function(p){return '<li>'+elEsc(p)+'</li>'}).join('');
  var linhas = [
    ['<th colspan=2>Jacobiano</th>',''],
    ['m&iacute;nimo', elNum(l.jac_min,3)],
    ['p1 &middot; mediana &middot; p99',
     elNum(l.jac_p01,3)+' &middot; '+elNum(l.jac_mediana,3)+' &middot; '
     +elNum(l.jac_p99,3)],
    ['m&aacute;ximo', elNum(l.jac_max,3)],
    ['voxels que DOBRAM', (l.dobras||0)+' ('+elNum(l.dobras_parte,4)+'%)'],
    ['<th colspan=2>Ida-e-volta (mm)</th>',''],
    ['mediana &middot; p95', elNum(l.consist_mediana,3)+' &middot; '
     +elNum(l.consist_p95,3)],
    ['m&aacute;ximo', elNum(l.consist_max,3)]
  ].concat(elLinhasDoAr(l.ar)).concat([
    ['<th colspan=2>Deslocamento (mm)</th>',''],
    ['mediana &middot; p95', elNum(l.desloc_mediana)+' &middot; '
     +elNum(l.desloc_p95)],
    ['m&aacute;ximo', elNum(l.desloc_max)],
    ['<th colspan=2>Base</th>',''],
    ['voxels no corpo', String(l.n_voxels||0)],
    ['cobertura da m&oacute;vel no corpo',
     (l.cobertura_parte===null||l.cobertura_parte===undefined) ? '&mdash;'
       : elNum(l.cobertura_parte,0)+'%'],
    ['partida do r&iacute;gido', d.inicio==='coordenadas'
       ? 'coordenadas do aparelho' : (d.inicio==='centros'
       ? 'centros das s&eacute;ries' : '&mdash;')],
    ['intensidade', (d.hu||[]).length===2 && d.hu[0] && d.hu[1] ? 'HU'
       : 'sinal sem unidade &mdash; janela por s&eacute;rie'],
    ['m&eacute;trica do deform&aacute;vel', d.so_rigido ? '&mdash;'
       : (l.metrica_no_corpo ? 'no corpo, onde a m&oacute;vel tem imagem'
       : 'a grade inteira')],
    ['malha', d.so_rigido || l.malha===null || l.malha===undefined
       ? '&mdash;' : String(l.malha)],
    ['motor', d.so_rigido?'s&oacute; r&iacute;gido':'B-spline livre'],
    ['grade', (d.grade||'')]
  ]);
  var tt = d.tempos||[], soma = 0;
  if(tt.length){
    linhas.push(['<th colspan=2>Tempo (s)</th>','']);
    tt.forEach(function(p){ soma += Number(p[1])||0;
      linhas.push([elEsc(p[0]), elNum(p[1],1)]) });
    linhas.push(['<b>ciclo inteiro</b>', '<b>'+elNum(soma,1)+'</b>']);
  }
  el('el-tab').innerHTML = linhas.map(function(r){
    return r[1]===''? '<tr>'+r[0]+'</tr>'
      : '<tr><td>'+r[0]+'</td><td>'+r[1]+'</td></tr>' }).join('');
}

function elIrAoCorte(z){
  if(!elPronto || isNaN(z)) return;
  elZ = Math.max(0, Math.min(elNZ-1, z));
  el('el-z').value = String(elZ);
  elCorte();
}

function elCorte(){
  if(!elJ || !elPronto){ return }
  var q='j='+encodeURIComponent(elJ)+'&z='+elZ+'&vista='+elVista;
  el('el-img').src='/api/elastic/corte?'+q;
  el('el-zrot').textContent = (elZ+1)+' / '+elNZ;
  elSobreposicao();
}

function elImagemFalhou(){
  if(!elPronto || !elJ || !el('el-img').getAttribute('src')) return;
  elPedir('/api/elastic/estado?j='+encodeURIComponent(elJ)).catch(function(e){
    if(e && e.semResposta) elFalha(e, elCorte);
  });
}

function elSobreposicao(){
  if(!elJ || !elPronto){ return }
  var svg=el('el-svg');
  var g=el('el-vgrade').checked, s=el('el-vsetas').checked;
  var d=(elVista==='jacobiano');
  if(!g && !s && !d){ svg.innerHTML=''; el('el-cortou').textContent=''; return }
  elPedir('/api/elastic/sobre?j='+encodeURIComponent(elJ)+'&z='+elZ
        +'&grade='+(g?1:0)+'&setas='+(s?1:0)+'&dobras='+(d?1:0))
   .then(function(o){
    if(o.erro){ svg.innerHTML=''; return }
    svg.setAttribute('viewBox','0 0 '+o.nx+' '+o.ny);
    var p=[];
    (o.grade||[]).forEach(function(ln){
      if(ln.length<2){ return }
      p.push('<polyline class="el-grade" points="'
        + ln.map(function(q){return q[0].toFixed(1)+','+q[1].toFixed(1)})
             .join(' ') + '"/>');
    });
    (o.setas||[]).forEach(function(a){
      p.push('<line class="el-seta" x1="'+a[0]+'" y1="'+a[1]+'" x2="'
        + a[2].toFixed(1)+'" y2="'+a[3].toFixed(1)+'"/>');
    });
    (o.dobras||[]).forEach(function(q){
      p.push('<rect class="el-dobra" x="'+q[0]+'" y="'+q[1]
             +'" width="1" height="1"/>');
    });
    svg.innerHTML=p.join('');
    el('el-cortou').textContent = o.cortou
      ? ('Marcadas ' + (o.dobras||[]).length + ' de ' + o.dobras_total
         + ' dobras deste corte — o desenho tem teto, o laudo não.') : '';
   }).catch(function(e){
    svg.innerHTML='';
    if(e && e.semResposta) elFalha(e, elSobreposicao);
   });
}

function elRetomar(){
  elPedir('/api/elastic/varredura?v=').then(function(d){
    elPintar(d, !!d.buscando);
    if(d.buscando && d.v){
      elV=d.v; elBuscaMostrar(true); elBuscaContar(d); elBuscaSeguir() }
  }).catch(function(e){ elFalha(e, elRetomar) });
}

document.addEventListener('DOMContentLoaded', function(){
  el('el-procurar').addEventListener('click', elProcurar);
  el('el-buscar').addEventListener('click', function(){ elVarrer(false) });
  el('el-mais').addEventListener('click', function(){ elVarrer(true) });
  el('el-parar').addEventListener('click', elPararBusca);
  el('el-denovo').addEventListener('click', elTentarDeNovo);
  el('el-fundir').addEventListener('click', elFundir);
  el('el-img').addEventListener('error', elImagemFalhou);
  el('el-tab').addEventListener('click', function(ev){
    var b = (ev.target && ev.target.closest) ? ev.target.closest('.el-ir') : null;
    if(b) elIrAoCorte(parseInt(b.getAttribute('data-z'),10));
  });
  el('el-z').addEventListener('input', function(){
    elZ=parseInt(this.value,10); elCorte() });
  el('el-lista').addEventListener('click', function(ev){
    var b = (ev.target && ev.target.closest) ? ev.target.closest('.el-it') : null;
    if(b) elEscolher(b.getAttribute('data-b'), b.textContent);
  });
  elPopup();
  el('el-vgrade').addEventListener('change', elSobreposicao);
  el('el-vsetas').addEventListener('change', elSobreposicao);
  Array.prototype.forEach.call(
    document.querySelectorAll('.el-vista'), function(b){
      b.addEventListener('click', function(){
        Array.prototype.forEach.call(document.querySelectorAll('.el-vista'),
          function(o){ o.classList.remove('on') });
        b.classList.add('on'); elVista=b.getAttribute('data-v');
        el('el-legenda').innerHTML = b.getAttribute('data-leg')||'';
        elCorte();
      });
    });
  elRetomar();
});
"""

PAGINA = u"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fus&atilde;o el&aacute;stica &middot; Elastic RT</title>
<style>@CSS@</style></head><body><div class="el-wrap">

@CABECA@

<div class="ui-cartoes el-cartoes">@CARTOES@</div>

<div class="el-topo">
  <div class="el-campo" style="min-width:140px;flex:0">
    <label>Grade (mm)</label>
    <select id="el-esp">
      <option value="3">3,0 &mdash; r&aacute;pida</option>
      <option value="2" selected>2,0 &mdash; padr&atilde;o</option>
      <option value="1.5">1,5 &mdash; lenta</option>
    </select></div>
  <div class="el-campo" style="min-width:140px;flex:0">
    <label>Malha</label>
    <select id="el-malha">
      <option value="6">6 &mdash; r&iacute;gida</option>
      <option value="8" selected>8 &mdash; padr&atilde;o</option>
      <option value="12">12 &mdash; livre</option>
    </select></div>
  <label class="el-chk" style="padding-bottom:9px">
    <input id="el-sorig" type="checkbox"> s&oacute; r&iacute;gida</label>
  <button id="el-fundir" class="el-bt" type="button" disabled>Fundir</button>
</div>
<div class="el-sujeitos" id="el-sujeitos" role="note" hidden><span class="pt"
  aria-hidden="true"></span><span data-radai-frase>@SUJEITOS@</span></div>

<div class="el-erro" id="el-erro"></div>
<div class="el-falha" id="el-falha" role="alert" hidden><span
  id="el-falha-txt"></span><span id="el-falha-cod"></span><button id="el-denovo"
  class="el-bt2" type="button">Tentar de novo</button></div>

<div class="el-prog" id="el-prog">
  <div class="el-barra"><i id="el-pct"></i></div>
  <div class="el-fase" id="el-fase"></div>
</div>

<div class="el-corpo" id="el-corpo">
  <div>
    <div class="el-vistas">@VISTAS@</div>
    <div class="el-palco" id="el-palco">
      <img id="el-img" alt="">
      <svg id="el-svg" preserveAspectRatio="none"></svg>
    </div>
    <div class="el-linha">
      <span id="el-zrot" style="font-size:12px;color:var(--txt-fraco);
        min-width:70px"></span>
      <input id="el-z" type="range" min="0" max="1" value="0">
      <label class="el-chk"><input id="el-vgrade" type="checkbox"> grade
        deformada</label>
      <label class="el-chk"><input id="el-vsetas" type="checkbox"> setas do
        campo</label>
    </div>
    <div class="el-legenda" id="el-legenda">@LEG0@</div>
    <div class="el-legenda" id="el-cortou"></div>
  </div>

  <div class="el-laudo">
    <div class="el-vered" id="el-vered"></div>
    <ul class="el-porques" id="el-porques"></ul>
    <table class="el-tab"><tbody id="el-tab"></tbody></table>
    <div class="el-nota">@REFNOSSA@</div>
    <div class="el-nota">@LIMIAR@</div>
  </div>
</div>

@ALERTA@

</div>
@ESCOLHA@
<script>@JS@</script>
</body></html>"""


PASTA_HTML = u"""<div class="el-topo">
  <div class="el-campo" style="flex:2">
    <label>Pasta com as s&eacute;ries</label>
    <input id="el-pasta" type="text" placeholder="deixe vazio para usar o ROOT configurado">
  </div>
  <button id="el-procurar" class="ui-bt" type="button">@ICO_PASTA@<span
    data-radai-frase>Procurar&hellip;</span></button>
  <button id="el-buscar" class="el-bt2" type="button">Procurar s&eacute;ries</button>
  <button id="el-mais" class="el-bt2" type="button">Adicionar outra pasta</button>
</div>

<div class="el-legenda">@SOMA@</div>

<div class="el-busca" id="el-busca" role="status" hidden>
  <div class="el-busca-barra" aria-hidden="true"><i></i></div>
  <div class="el-busca-lin">
    <span data-radai-frase>Procurando s&eacute;ries&hellip;</span>
    <b id="el-busca-pastas">0</b><span data-radai-frase>pastas olhadas</span>&middot;
    <b id="el-busca-arqs">0</b><span data-radai-frase>arquivos lidos</span>&middot;
    <b id="el-busca-series">0</b><span data-radai-frase>s&eacute;ries achadas</span>
    <button id="el-parar" class="el-bt2" type="button">Parar a busca</button>
  </div>
</div>

<div class="el-pastas" id="el-pastas"></div>
<div class="el-avisos" id="el-avisos"></div>
<div class="el-lista" id="el-lista" role="listbox" aria-label="s&eacute;ries"></div>"""

CARTAO_MOVEL = u"Carregar imagem a ser deformada"
CARTAO_FIXA = u"Carregar imagem de destino"


def _escolha():
    import radai_tabela_acervo
    import radai_ui
    abas = radai_ui.abas_de_serie(
        u"el_origem",
        [(u"acervo", u"Acervo local", radai_tabela_acervo.html(u"el_acervo")),
         (u"pasta", u"Aponte uma pasta", PASTA_HTML)],
        cor_var=u"--mod-elastic")
    return radai_ui.popup_de_serie(u"el_escolha", abas)


def _cartoes():
    import radai_ui
    return (radai_ui.cartao_de_serie(u"el-movel", u"el_escolha", CARTAO_MOVEL,
                                     vazio=u"nenhuma série escolhida",
                                     chave_modulo=u"elastic", contexto=u"movel")
            + radai_ui.cartao_de_serie(u"el-fixa", u"el_escolha", CARTAO_FIXA,
                                       vazio=u"nenhuma série escolhida",
                                       chave_modulo=u"elastic",
                                       contexto=u"fixa"))


def _vistas():
    p = []
    for i, (chave, rot, leg) in enumerate(ROTULOS):
        p.append(u'<button class="el-vista%s" type="button" data-v="%s" '
                 u'data-leg="%s">%s</button>'
                 % (u" on" if chave == "xadrez" else u"", chave, leg, rot))
    return u"".join(p)


def pagina():
    import radai_ui
    import json
    return (PAGINA.replace("@CSS@", CSS)
                  .replace("@ESCOLHA@", _escolha())
                  .replace("@CARTOES@", _cartoes())
                  .replace("@JS@", JS.replace("@CARTAO_FIXA_JS@", json.dumps(CARTAO_FIXA, ensure_ascii=False))
                                     .replace("@CARTAO_MOVEL_JS@", json.dumps(CARTAO_MOVEL, ensure_ascii=False))
                                     .replace("@SUJEITOS_LAUDO_JS@", json.dumps(SUJEITOS_NO_LAUDO, ensure_ascii=False)))
                  .replace("@SUJEITOS@", SUJEITOS_DIFERENTES)
                  .replace("@ICO_PASTA@", radai_ui.icone(u"pasta"))
                  .replace("@VISTAS@", _vistas())
                  .replace("@LEG0@", ROTULOS[4][2])
                  .replace("@SOMA@", SOMA)
                  .replace("@CABECA@", _cabeca())
                  .replace("@ALERTA@", _alerta())
                  .replace("@REFNOSSA@", radai_elastic.REFERENCIA_E_NOSSA)
                  .replace("@LIMIAR@", radai_elastic.LIMIAR_E_NOSSO))


def _cabeca():
    import radai_modules
    import radai_ui
    ajuda = radai_ui.ajuda(radai_elastic.NAO_PROPAGA)
    return radai_ui.cabeca_de_funcao(
        u"\u29c9", u"Fus\u00e3o el\u00e1stica",
        radai_modules.MODULOS["elastic"]["frase"], ajuda, u"elastic")


def _alerta():
    import radai_ui
    return radai_ui.alerta(radai_elastic.SEM_APROVACAO)


SUJEITOS_DIFERENTES = (u"As duas séries têm identificação de paciente diferente "
                       u"— confira se são da mesma pessoa antes de usar a fusão.")
SUJEITOS_NO_LAUDO = u"as duas séries têm identificação de paciente diferente"
ESCOLHA_DUAS = u"Escolha duas séries diferentes."
JA_NA_LISTA = (u"Esta pasta já está na lista, com o número [%s]. Para varrê-la de novo, "
               u"tire-a da lista antes.")
FUSAO_EM_ANDAMENTO = (u"Já há uma fusão em andamento (%s). Duas ao mesmo tempo "
                      u"disputam a CPU e fazem as duas demorarem o dobro.")


def identidade_da_serie(pasta, uid=u""):
    if not pasta or not os.path.isdir(pasta):
        return None
    try:
        import pydicom
    except Exception:
        return None
    try:
        nomes = sorted(os.listdir(pasta))[:600]
    except OSError:
        return None
    for n in nomes:
        c = os.path.join(pasta, n)
        if not os.path.isfile(c):
            continue
        try:
            ds = pydicom.dcmread(c, stop_before_pixels=True, specific_tags=[
                "PatientID", "PatientBirthDate", "SeriesInstanceUID"])
        except Exception:
            continue
        if uid and str(getattr(ds, "SeriesInstanceUID", "") or "") != str(uid):
            continue
        return (str(getattr(ds, "PatientID", "") or "").strip(),
                str(getattr(ds, "PatientBirthDate", "") or "").strip())
    return None


def sujeitos_diferentes(id_a, id_b):
    if not id_a or not id_b or not id_a[0] or not id_b[0]:
        return None
    if id_a[0].upper() != id_b[0].upper():
        return True
    return bool(id_a[1] and id_b[1] and id_a[1] != id_b[1])


PESO = ((u"preparando", 6), (u"rígido", 14), (u"deformável", 50),
        (u"campo", 8), (u"inverso", 12), (u"reamostrando", 5), (u"laudo", 5))


def tempos_das_fases(marcas, fim):
    fora = []
    for i, (fase, t0) in enumerate(marcas):
        t1 = marcas[i + 1][1] if i + 1 < len(marcas) else fim
        fora.append((fase, round(max(0.0, t1 - t0), 1)))
    return fora


def janela_da_vista(r, vista):
    hu = tuple(r.get("hu") or (True, True))
    if all(hu) or not r.get("janelas"):
        return JANELAS.get(vista, (40, 400)), False
    if vista in VISTAS_EM_COR:
        return JANELAS[vista], False
    if vista == "fixa":
        return tuple(r["janelas"]["fixa"]), False
    if vista in ("rigida", "fundida"):
        return tuple(r["janelas"]["movel"]), False
    if vista == "diferenca":
        return (0.25, 0.5), True
    return (0.5, 1.0), True


def _normalizada(a, janela):
    import numpy as np
    c, w = janela
    return np.clip((np.asarray(a, dtype=np.float32) - (c - w / 2.0))
                   / max(1e-6, float(w)), 0.0, 1.0)


COR_COMPRIME = (70, 150, 255)
COR_EXPANDE = (255, 150, 40)
COR_DOBRA = (255, 40, 40)
JAC_ESCALA_LOG2 = 1.0


def regiao_do_corte(r, z):
    import numpy as np
    d = (r or {}).get("dentro")
    if d is None:
        return None
    d = np.asarray(d, dtype=bool)
    if d.ndim != 3 or not (0 <= int(z) < d.shape[0]):
        return None
    return d[int(z)]


def pontos_de_dobra(jz, onde=None):
    import numpy as np
    m = np.asarray(jz) < radai_elastic.JAC_DOBRA
    if onde is not None and np.shape(onde) == m.shape:
        m &= np.asarray(onde, dtype=bool)
    return np.nonzero(m)


def jacobiano_em_cor(j, fundo, onde=None):
    import numpy as np
    j = np.asarray(j, dtype=np.float64)
    g = np.clip(np.asarray(fundo, dtype=np.float64), 0.0, 1.0) * 255.0
    rgb = np.repeat(g[..., None], 3, axis=2)
    dobra = j <= 0.0
    lg = np.log2(np.where(dobra, 1.0, np.maximum(j, 1e-6)))
    t = np.clip(lg / JAC_ESCALA_LOG2, -1.0, 1.0)
    alfa = (np.abs(t) ** 0.7) * 0.85
    if onde is not None and np.shape(onde) == j.shape:
        fora = ~np.asarray(onde, dtype=bool)
        alfa = np.where(fora, 0.0, alfa)
        dobra = dobra & ~fora
    for k in range(3):
        cor = np.where(t < 0, COR_COMPRIME[k], COR_EXPANDE[k])
        rgb[..., k] = rgb[..., k] * (1.0 - alfa) + cor * alfa
        rgb[..., k][dobra] = COR_DOBRA[k]
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


COR_IDA_E_VOLTA = (240, 196, 64)


def ida_e_volta_em_cor(res, fundo, onde=None):
    import numpy as np
    g = np.clip(np.asarray(fundo, dtype=np.float64), 0.0, 1.0) * 255.0
    rgb = np.repeat(g[..., None], 3, axis=2)
    if res is not None and np.shape(res) == g.shape:
        r = np.nan_to_num(np.asarray(res, dtype=np.float64),
                          nan=IDA_E_VOLTA_PLENA_MM,
                          posinf=IDA_E_VOLTA_PLENA_MM)
        t = np.clip(r / IDA_E_VOLTA_PLENA_MM, 0.0, 1.0)
        alfa = (t ** 0.7) * 0.9
        if onde is not None and np.shape(onde) == t.shape:
            alfa = np.where(np.asarray(onde, dtype=bool), alfa, 0.0)
        for k in range(3):
            rgb[..., k] = rgb[..., k] * (1.0 - alfa) + COR_IDA_E_VOLTA[k] * alfa
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def png_rgb(rgb):
    import struct
    import zlib
    import numpy as np
    a = np.ascontiguousarray(rgb, dtype=np.uint8)
    alt, larg = a.shape[:2]
    cru = b"".join(b"\x00" + a[y].tobytes() for y in range(alt))

    def bloco(tipo, dados):
        c = struct.pack(">I", len(dados)) + tipo + dados
        return c + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + bloco(b"IHDR", struct.pack(">IIBBBBB", larg, alt, 8, 2, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(cru, 6)) + bloco(b"IEND", b""))


def montar(app):
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    # GUARDA: uma fusao por vez, e o resultado fica na memoria da sessao: nao
    # vai para o disco.
    _T = {"atual": None}
    _TRAVA = threading.Lock()

    _P = {"lista": []}
    _TRAVA_P = threading.Lock()

    def _pasta_de(b):
        import radai_thumbnail
        p, uid = radai_thumbnail.resolver(b)
        return p, uid

    def _sujeitos(bf, bm):
        try:
            return sujeitos_diferentes(identidade_da_serie(*_pasta_de(bf)),
                                       identidade_da_serie(*_pasta_de(bm)))
        except Exception:
            return None

    @app.post("/api/elastic/par")
    async def _par(request: Request):
        try:
            c = await request.json() or {}
            bf, bm = str(c.get("fixa") or ""), str(c.get("movel") or "")
            if not bf or not bm or bf == bm:
                return JSONResponse({"sujeitos_diferentes": None})
            return JSONResponse({"sujeitos_diferentes": await radai_web.no_threadpool(
                _sujeitos, bf, bm)})
        except Exception:
            return JSONResponse({"sujeitos_diferentes": None})

    @app.get("/elastic/fusao", response_class=HTMLResponse)
    def _tela():
        return radai_menu.aplicar(pagina(), "elastic_fusao")

    _V = {"atual": None}

    def _assentar(v):
        import radai_thumbnail
        if v["assentada"]:
            return
        base = _P["lista"] if v["acumular"] else []
        lista, avisos = acumular_pasta(base, v["pasta"], achadas(v),
                                       radai_thumbnail.bilhete)
        _P["lista"] = lista
        v["avisos"] = avisos + avisos_da_varredura(v)
        v["assentada"] = True

    def _parar(v):
        if v and not v["fim"] and not v["parado"]:
            v["parado"] = True
            _assentar(v)

    def _buscando(v):
        return bool(v) and not v["fim"] and not v["parado"] and not v["erro"]

    def _resposta(v=None, erro=None):
        import radai_thumbnail
        with _TRAVA_P:
            if v is not None and not v["assentada"] and not v["erro"]:
                base = _P["lista"] if v["acumular"] else []
                lista, avisos = acumular_pasta(
                    base, v["pasta"], achadas(v),
                    radai_thumbnail.bilhete)
            else:
                lista = _P["lista"]
                avisos = list((v or {}).get("avisos") or [])
            d = para_a_tela(lista)
        d["avisos"] = avisos
        if v is not None:
            d.update(v=v["v"], buscando=_buscando(v),
                     pastas_olhadas=int(v["pastas"]),
                     arquivos=int(v["arquivos"]),
                     series_achadas=len(v.get("series") or ()))
            if v["erro"]:
                d["erro"] = v["erro"]
        if erro:
            d["erro"] = erro
        return d

    def _trabalhar_busca(v):
        try:
            varrer_pasta(v)
        finally:
            with _TRAVA_P:
                if not v["parado"] and (not v["erro"] or v.get("series")):
                    _assentar(v)
                v["fim"] = True

    @app.post("/api/elastic/series")
    async def _series(request: Request):
        try:
            c = await request.json() or {}
            import radai_config
            pasta = str(c.get("pasta") or "").strip()
            acumular = bool(c.get("acumular"))
            if not pasta:
                pasta = radai_config.root_configurado()
            if not pasta:
                return JSONResponse(_resposta(None, erro=SEM_ROOT))
            with _TRAVA_P:
                ja = indice_de_pasta(_P["lista"], pasta) if acumular else 0
                if not ja:
                    _parar(_V.get("atual"))
                    v = nova_varredura(pasta, acumular)
                    _V["atual"] = v
            if ja:
                return JSONResponse(_resposta(None, erro=JA_NA_LISTA % ja))
            threading.Thread(target=_trabalhar_busca, args=(v,),
                             daemon=True).start()
            return JSONResponse(_resposta(v))
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)})

    @app.get("/api/elastic/varredura")
    def _varredura(v: str = ""):
        try:
            a = _V.get("atual")
            if not v:
                return JSONResponse(_resposta(a if _buscando(a) else None))
            if not a or a["v"] != v:
                return JSONResponse(_resposta(None, erro=BUSCA_DESCONHECIDA))
            return JSONResponse(_resposta(a))
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)})

    @app.post("/api/elastic/parar_busca")
    async def _parar_busca(request: Request):
        try:
            c = await request.json() or {}
            a = _V.get("atual")
            if not a or a["v"] != str(c.get("v") or ""):
                return JSONResponse(_resposta(None))
            with _TRAVA_P:
                _parar(a)
            return JSONResponse(_resposta(a))
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)})

    @app.post("/api/elastic/remover_pasta")
    async def _remover_pasta(request: Request):
        try:
            c = await request.json() or {}
            with _TRAVA_P:
                lista, fora = tirar_pasta(_P["lista"], c.get("n"))
                _P["lista"] = lista
            d = para_a_tela(lista)
            d["avisos"] = ([] if fora is not None else
                           [u"Não havia pasta com esse número na lista — ela "
                            u"pode ter sido tirada noutra aba."])
            return JSONResponse(d)
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)})

    @app.post("/api/elastic/fundir")
    async def _fundir(request: Request):
        try:
            c = await request.json() or {}
            bf, bm = str(c.get("fixa") or ""), str(c.get("movel") or "")
            if bf == bm or not bf or not bm:
                return JSONResponse({"erro": ESCOLHA_DUAS})
            with _TRAVA:
                a = _T.get("atual")
                if a and not a.get("pronto") and not a.get("erro"):
                    return JSONResponse({
                        "erro": FUSAO_EM_ANDAMENTO % a.get("fase", u"")})
                t = {"j": os.urandom(8).hex(), "fase": u"na fila", "pct": 0,
                     "pronto": False, "erro": None, "r": None,
                     "so_rigido": bool(c.get("so_rigido"))}
                _T["atual"] = t

            def trabalhar():
                try:
                    with _TRAVA_P:
                        sf = serie_do_bilhete(_P["lista"], bf)
                        sm = serie_do_bilhete(_P["lista"], bm)
                    if sf is None:
                        pf, uf = _pasta_de(bf)
                        sf = {"pasta": pf, "uid": uf} if pf else None
                    if sm is None:
                        pm, um = _pasta_de(bm)
                        sm = {"pasta": pm, "uid": um} if pm else None
                    if not sf or not sm:
                        raise ValueError(
                            u"Bilhete expirado — o programa foi reiniciado "
                            u"desde que esta lista foi montada. Clique em "
                            u"«Procurar séries» de novo.")
                    t["sujeitos_diferentes"] = sujeitos_diferentes(
                        identidade_da_serie(sf.get("pasta"), sf.get("uid")),
                        identidade_da_serie(sm.get("pasta"), sm.get("uid")))
                    t["fase"] = u"lendo as séries"
                    fixa = carregar_serie(sf)
                    movel = carregar_serie(sm)

                    total = float(sum(p for _n, p in PESO))

                    marcas = []

                    def prog(fase, it, val):
                        if it < 0:
                            marcas.append((fase, time.time()))
                        for i, (n, _p) in enumerate(PESO):
                            if n == fase:
                                antes = sum(p for _x, p in PESO[:i])
                                t["fase"] = (u"%s (passo %d)" % (fase, it)
                                             if it >= 0 else fase)
                                t["pct"] = int(100.0 * antes / total)
                                return
                        t["fase"] = fase

                    r = radai_elastic.fundir(
                        fixa, movel, esp_mm=float(c.get("esp") or 2.0),
                        malha=int(c.get("malha") or 8), prog=prog,
                        so_rigido=bool(c.get("so_rigido")))
                    t["tempos"] = tempos_das_fases(marcas, time.time())
                    t["r"] = r
                    t["pct"] = 100
                    t["fase"] = u"pronto"
                    t["pronto"] = True
                except Exception as e:
                    t["erro"] = u"%s: %s" % (type(e).__name__, e)
                    t["fase"] = u"falhou"

            threading.Thread(target=trabalhar, daemon=True).start()
            return JSONResponse({"j": t["j"]})
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)})

    def _tarefa(j):
        a = _T.get("atual")
        return a if (a and a.get("j") == str(j or "")) else None

    @app.get("/api/elastic/estado")
    def _estado(j: str = ""):
        t = _tarefa(j)
        if not t:
            return JSONResponse({"erro": u"Tarefa desconhecida — o programa "
                                        u"pode ter sido reiniciado."})
        d = {"fase": t.get("fase"), "pct": t.get("pct"),
             "pronto": t.get("pronto"), "erro": t.get("erro"),
             "so_rigido": t.get("so_rigido"),
             "sujeitos_diferentes": t.get("sujeitos_diferentes")}
        r = t.get("r")
        if t.get("pronto") and r:
            tam = r["fixa"].GetSize()
            d["laudo"] = r["laudo"]
            d["nz"] = int(tam[2])
            d["nx"], d["ny"] = int(tam[0]), int(tam[1])
            d["grade"] = u"%d × %d × %d @ %.1f mm" % (
                tam[0], tam[1], tam[2], r["fixa"].GetSpacing()[0])
            d["inicio"] = r.get("inicio") or u""
            d["hu"] = list(r.get("hu") or (True, True))
            d["tempos"] = t.get("tempos") or []
        return JSONResponse(d)

    def _plano(t, vista, z):
        conferir_laudo(t, vista)
        import numpy as np
        import SimpleITK as sitk
        r = t["r"]
        z = max(0, min(r["fixa"].GetSize()[2] - 1, int(z)))
        jan, norm = janela_da_vista(r, vista)
        af = sitk.GetArrayViewFromImage(r["fixa"])[z]
        if vista == "fixa":
            return af, jan, False
        if vista == "rigida":
            return sitk.GetArrayViewFromImage(r["movel_rig"])[z], jan, False
        au = sitk.GetArrayViewFromImage(r["fundida"])[z]
        if vista == "fundida":
            return au, jan, False
        if vista == "jacobiano":
            jj = r.get("jac")
            if jj is None:
                jj = radai_elastic.jacobiano(r["campo"])
            jz = sitk.GetArrayViewFromImage(jj)[z]
            fundo = _normalizada(af, janela_da_vista(r, "fixa")[0])
            return (jacobiano_em_cor(jz, fundo, onde=regiao_do_corte(r, z)),
                    None, False)
        if vista == "ida_e_volta":
            cr = r.get("consist")
            fundo = _normalizada(af, janela_da_vista(r, "fixa")[0])
            return (ida_e_volta_em_cor(None if cr is None else cr[z], fundo,
                                       onde=regiao_do_corte(r, z)),
                    None, False)
        if norm:
            jf = janela_da_vista(r, "fixa")[0]
            jm = janela_da_vista(r, "fundida")[0]
            af = _normalizada(af, jf)
            au = _normalizada(au, jm)
        if vista == "diferenca":
            return np.abs(np.asarray(af, np.float32) - au), jan, norm
        outra = (sitk.GetArrayViewFromImage(r["movel_rig"])[z]
                 if vista == "xadrez_rig" else au)
        if norm and vista == "xadrez_rig":
            outra = _normalizada(outra, janela_da_vista(r, "rigida")[0])
        n = 8
        a = np.array(af, dtype=np.float32, copy=True)
        ys, xs = np.indices(a.shape)
        bloco = ((ys * n // a.shape[0]) + (xs * n // a.shape[1])) % 2 == 1
        a[bloco] = np.asarray(outra, dtype=np.float32)[bloco]
        return a, jan, norm

    @app.get("/api/elastic/corte")
    def _corte(j: str = "", z: int = 0, vista: str = "fixa"):
        t = _tarefa(j)
        if not t or not t.get("pronto"):
            return Response(status_code=404)
        if vista not in VISTAS:
            return Response(status_code=400)
        try:
            import radai_recon3d
            a, jan, _norm = _plano(t, vista, z)
            if jan is None:
                png = png_rgb(a)
            else:
                c, l = jan
                png = radai_recon3d.para_png(a, c, l)
            return Response(content=png, media_type="image/png",
                            headers={"Cache-Control": "no-store"})
        except SemLaudo as e:
            return JSONResponse({"erro": str(e)}, status_code=409)
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)},
                                status_code=500)

    @app.get("/api/elastic/sobre")
    def _sobre(j: str = "", z: int = 0, grade: int = 0, setas: int = 0,
               dobras: int = 0):
        t = _tarefa(j)
        if not t or not t.get("pronto"):
            return JSONResponse({"erro": u"sem tarefa"}, status_code=404)
        try:
            import numpy as np
            import SimpleITK as sitk
            r = t["r"]
            tam = r["fixa"].GetSize()
            z = max(0, min(tam[2] - 1, int(z)))
            d = {"nx": int(tam[0]), "ny": int(tam[1]), "cortou": False,
                 "dobras_total": 0}
            if grade:
                d["grade"] = radai_elastic.grade_deformada(
                    r["campo"], z, passo=max(6, tam[0] // 18))
            if setas:
                d["setas"] = [[a[0], a[1], a[2], a[3]]
                              for a in radai_elastic.setas(
                                  r["campo"], z,
                                  passo=max(8, tam[0] // 14), escala=1.0)]
            if dobras:
                jv = r.get("jac")
                if jv is None:
                    jv = radai_elastic.jacobiano(r["campo"])
                jj = sitk.GetArrayViewFromImage(jv)[z]
                ys, xs = pontos_de_dobra(jj, regiao_do_corte(r, z))
                d["dobras_total"] = int(len(ys))
                if len(ys) > TETO_DOBRAS:
                    d["cortou"] = True
                    ys, xs = ys[:TETO_DOBRAS], xs[:TETO_DOBRAS]
                d["dobras"] = [[int(x), int(y)] for x, y in zip(xs, ys)]
            return JSONResponse(d)
        except Exception as e:
            return JSONResponse({"erro": u"%s: %s" % (type(e).__name__, e)},
                                status_code=500)
