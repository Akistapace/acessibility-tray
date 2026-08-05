# FaceMesh Mouse

Controle o mouse com a cabeça: a ponta do nariz move o cursor, e gestos
faciais (piscar, boca aberta, sobrancelha levantada) disparam clique
esquerdo/direito/duplo ou scroll — tudo configurável numa janela de
calibração. Depois de configurar, o tracking continua rodando em segundo
plano (sem janela visível), com ícone na bandeja e atalhos globais.

Ver [docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md](docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md)
para o design completo.

## Requisitos

- Windows, Python 3.11 (já usado neste projeto: `.venv` criado com
  `C:\Users\ferna\AppData\Local\Programs\Python\Python311\python.exe`)
- Webcam com permissão de câmera liberada no Windows

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
```

## Rodar

```powershell
.venv\Scripts\python run.py
```

Na primeira execução abre a janela de configuração:

1. Observe os indicadores `ear_a` / `ear_b` / `mouth_open_ratio` /
   `eyebrow_raise_ratio` enquanto faz cada gesto, pra saber qual reage a
   qual olho (os nomes "A"/"B" são só internos, sem relação fixa com
   esquerda/direita anatômica por causa do espelhamento da câmera).
2. Calibre a faixa de movimento: posicione a cabeça em cada extremo
   (cima/baixo/esquerda/direita) e clique em "Capturar".
3. Mapeie cada gesto pra uma ação de mouse no dropdown.
4. Clique em "Iniciar tracking" (ou feche a janela) — a câmera some da
   tela e o controle do mouse fica ativo em background.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair.
Atalhos globais: `Ctrl+Alt+P` pausa/retoma, `Ctrl+Alt+O` reabre a config.

Config salvo em `config.json` na raiz do projeto (ignorado pelo git).

## Testes

```powershell
.venv\Scripts\pytest
```

Cobre a lógica pura (motor de gestos, matemática de calibração/smoothing,
load/save de config) sem precisar de câmera real. Câmera, mouse, bandeja e
atalhos exigem checklist manual (ver spec).

## Build do executável (.exe)

```powershell
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --onefile --windowed --collect-data mediapipe --collect-all cv2 run.py
```

O executável fica em `dist/run.exe`. Pontos de atenção:

- Arquivo grande (~200–400MB) por causa do MediaPipe/OpenCV/NumPy embutidos.
- Primeira execução é mais lenta (descompacta pra pasta temporária).
- Exe não assinado → Windows SmartScreen avisa no primeiro uso.
- Precisa conceder permissão de câmera do Windows ao exe na primeira vez.
