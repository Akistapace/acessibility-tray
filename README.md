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

Na primeira execução abre a janela de configuração, em 3 passos:

1. **Calibrar movimento**: clique em "Gravar Cima/Baixo/Esquerda/Direita",
   mova a cabeça até o extremo desejado e clique em "Parar" — o valor mais
   extremo atingido durante a gravação é o que fica salvo, não precisa
   acertar o timing do clique. Ajuste "Zona morta" (ignora tremores
   pequenos) e "Sensibilidade" (velocidade do cursor) se necessário.
2. **Mapear gestos**: observe as barras `Olho A` / `Olho B` / `Boca aberta`
   / `Sobrancelha levantada` reagirem enquanto faz cada gesto, pra saber
   qual reage a qual olho (os nomes "A"/"B" são só internos, sem relação
   fixa com esquerda/direita anatômica por causa do espelhamento da
   câmera), e escolha uma ação de mouse pra cada gesto no dropdown.
3. **Iniciar**: clique em "Iniciar controle do mouse" (ou feche a janela)
   — a câmera some da tela e o controle do mouse fica ativo em background.

O cursor se move de forma relativa à cabeça, como um mouse físico: `Ctrl+Alt+P`
pausa e congela o cursor a qualquer momento — use pra "levantar o mouse",
reposicionar a cabeça numa posição mais confortável, e retomar exatamente de
onde parou, sem pular.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair. Clique com o botão
esquerdo no ícone também reabre a config direto; botão direito mostra o
menu completo.
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
.venv\Scripts\pyinstaller --onefile --windowed --paths src --collect-data mediapipe --collect-all cv2 -n facemesh-mouse run.py
```

`--paths src` é obrigatório: o código roda com `src/` adicionado ao
`sys.path` em tempo de execução (ver `run.py`), mas a análise estática do
PyInstaller não enxerga isso sozinha — sem essa flag o build "funciona"
mas o exe falha com `ModuleNotFoundError: No module named 'facemesh_mouse'`.

O executável fica em `dist/facemesh-mouse.exe` (~110MB testado). Pontos de
atenção:

- Arquivo grande (~200–400MB) por causa do MediaPipe/OpenCV/NumPy embutidos.
- Primeira execução é mais lenta (descompacta pra pasta temporária).
- Exe não assinado → Windows SmartScreen avisa no primeiro uso.
- Precisa conceder permissão de câmera do Windows ao exe na primeira vez.
