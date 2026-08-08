# FaceMesh Mouse

Controle o mouse com a cabeça: vários pontos do rosto são rastreados por
fluxo óptico e a média do movimento deles move o cursor, e nove gestos
faciais (piscar cada olho ou os dois, levantar cada sobrancelha ou as duas,
abrir a boca, mover a boca fechada para cada lado) disparam clique
esquerdo/direito/duplo ou scroll — tudo configurável numa janela de
calibração. Cada gesto tem um tempo de espera: você precisa segurar a
expressão por alguns décimos de segundo para ela valer, o que impede que
piscadas naturais virem cliques. Depois de configurar, o tracking continua
rodando em segundo plano (sem janela visível), com ícone na bandeja e
atalhos globais.

Ver [docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md](docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md)
(design original, com os cinco gestos v1 e sem `hold_ms`),
[docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md](docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md)
(nove gestos, tempo de espera e a UI atual em abas),
[docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md](docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md)
(cursor relativo por optical flow, sliders de sensibilidade/aceleração no
lugar da calibração de quatro pontos) e
[docs/superpowers/specs/2026-08-07-mouse-yield-and-click-feedback-design.md](docs/superpowers/specs/2026-08-07-mouse-yield-and-click-feedback-design.md)
(ceder controle ao mouse físico, pulso visual de clique e log local) para o
design completo.

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

Na primeira execução abre a janela de configuração: à esquerda ficam a
prévia da câmera e o botão persistente "Iniciar controle do mouse"; à
direita, três abas.

- **Movimento**: não há mais gravação de extremos — o cursor se move de
  forma relativa à cabeça, como um mouse de verdade. Quatro sliders ajustam
  esse movimento: sensibilidade horizontal e vertical (quanto o cursor anda
  para cada movimento da cabeça em cada eixo — a vertical costuma precisar
  ser maior, porque a cabeça se move menos nesse eixo), aceleração (deixa
  movimentos pequenos mais lentos e movimentos grandes mais rápidos, para
  mirar com precisão sem perder velocidade) e limiar de movimento (ignora
  tremores menores que um certo número de pixels, pra ajudar o cursor a
  parar completamente). Um interruptor liga o clique por permanência
  (dwell click): com um slider ao lado ajustando o tempo, o clique esquerdo
  dispara sozinho quando o cursor fica parado sobre um elemento, sem
  precisar de gesto — desligado por padrão.
- **Gestos**: nove gestos, cada um com uma barra que enche conforme você se
  aproxima de dispará-lo. Faça a expressão e veja qual barra reage pra saber
  qual é qual (os nomes "A"/"B" de olho e sobrancelha são só internos, sem
  relação fixa com esquerda/direita anatômica por causa do espelhamento da
  câmera; já a boca para os lados segue o que você vê no preview). Escolha a
  ação de mouse de cada gesto e, no slider ao lado, por quanto tempo a
  expressão precisa ser segurada pra valer (padrão 400ms — bem acima de uma
  piscada natural, que dura ~100-150ms).
- **Ajuda**: o mesmo resumo de uso e atalhos, dentro da própria janela.

Quando terminar de ajustar o movimento e mapear os gestos, clique em "Iniciar controle
do mouse" (ou feche a janela) — a janela some e o controle do mouse fica
ativo em background.

O cursor se move de forma relativa à cabeça, como um mouse físico: `Ctrl+Alt+P`
pausa e congela o cursor a qualquer momento — use pra "levantar o mouse",
reposicionar a cabeça numa posição mais confortável, e retomar exatamente de
onde parou, sem pular.

Se você mexer no mouse físico ou no trackpad enquanto o controle pela cabeça
está ativo, o app cede o controle na hora: o cursor obedece o mouse físico e
a cabeça é ignorada até você parar de mexer por alguns segundos (padrão 3s,
ajustável em Movimento). O ícone da bandeja fica azul enquanto isso.

Ícone na bandeja: Pausar/Retomar, Reabrir Config, Sair. Clique com o botão
esquerdo no ícone também reabre a config direto; botão direito mostra o
menu completo.
Atalhos globais: `Ctrl+Alt+P` pausa/retoma, `Ctrl+Alt+O` reabre a config.

Cada clique disparado por gesto mostra um pulso azul na posição do cursor,
pra confirmar visualmente que o clique aconteceu — útil porque piscar ou
levantar a sobrancelha não tem o retorno tátil de um clique físico.

Todo clique também fica registrado em `clicks.log` (data, gesto, ação,
posição e a janela em foco), rotacionado automaticamente pra não crescer
sem limite; nunca é enviado pra lugar nenhum, e pode ser desligado na aba
Movimento.

Config salvo em `config.json` e histórico de cliques em `clicks.log`,
ambos na raiz do projeto (ignorados pelo git).

## Testes

```powershell
.venv\Scripts\pytest
```

Cobre a lógica pura (motor de gestos, poda de pontos e curva de aceleração,
cessão de controle ao mouse físico, log de cliques, load/save de config)
sem precisar de câmera real. Câmera, bandeja, atalhos e a aparência visual
do pulso exigem checklist manual (ver spec).

## Build do executável (.exe)

```powershell
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --onefile --windowed --paths src --collect-data mediapipe --collect-all cv2 --collect-data customtkinter -n facemesh-mouse run.py
```

`--paths src` é obrigatório: o código roda com `src/` adicionado ao
`sys.path` em tempo de execução (ver `run.py`), mas a análise estática do
PyInstaller não enxerga isso sozinha — sem essa flag o build "funciona"
mas o exe falha com `ModuleNotFoundError: No module named 'facemesh_mouse'`.

`--collect-data customtkinter` também é obrigatório: o CustomTkinter carrega
temas em JSON e fontes em tempo de execução, e a análise estática do
PyInstaller não enxerga esses arquivos — sem a flag o exe abre e quebra ao
montar a janela.

O executável fica em `dist/facemesh-mouse.exe` (~110MB testado). Pontos de
atenção:

- Arquivo grande (~200–400MB) por causa do MediaPipe/OpenCV/NumPy embutidos.
- Primeira execução é mais lenta (descompacta pra pasta temporária).
- Exe não assinado → Windows SmartScreen avisa no primeiro uso.
- Precisa conceder permissão de câmera do Windows ao exe na primeira vez.
