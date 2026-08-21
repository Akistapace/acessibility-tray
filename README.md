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
atalhos globais. O app não tem teclado próprio, mas o teclado virtual do
Windows pode ser aberto por um círculo flutuante e arrastável que fica
sempre visível na tela (canto inferior direito por padrão), pra quem
também precisar digitar. O teclado do Windows só abre se algum campo de
texto estiver com foco -- clique nele antes; se o círculo pulsar em
vermelho em vez de azul, foi isso que faltou.

Ver [docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md](docs/superpowers/specs/2026-08-05-facemesh-mouse-design.md)
(design original, com os cinco gestos v1 e sem `hold_ms`),
[docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md](docs/superpowers/specs/2026-08-07-gesture-expansion-modern-ui-design.md)
(nove gestos, tempo de espera e a UI atual em abas),
[docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md](docs/superpowers/specs/2026-08-07-optical-flow-tracking-design.md)
(cursor relativo por optical flow, sliders de sensibilidade/aceleração no
lugar da calibração de quatro pontos) e
[docs/superpowers/specs/2026-08-07-mouse-yield-and-click-feedback-design.md](docs/superpowers/specs/2026-08-07-mouse-yield-and-click-feedback-design.md)
(ceder controle ao mouse físico, pulso visual de clique e log local) e
[docs/superpowers/specs/2026-08-13-virtual-keyboard-launcher-design.md](docs/superpowers/specs/2026-08-13-virtual-keyboard-launcher-design.md)
(lançar o teclado virtual do Windows) e
[docs/superpowers/specs/2026-08-13-floating-keyboard-button-design.md](docs/superpowers/specs/2026-08-13-floating-keyboard-button-design.md)
(círculo flutuante e arrastável como único ponto de entrada, no lugar do
item na bandeja e do botão na aba Ajuda) e
[docs/superpowers/specs/2026-08-18-cursor-appearance-design.md](docs/superpowers/specs/2026-08-18-cursor-appearance-design.md)
(tamanho, cor e modo "mista" da seta real do Windows)
para o design completo.

## Requisitos

- Windows
- Webcam com permissão de câmera liberada no Windows

## Setup

```powershell
pnpm install
```

## Rodar (dev)

Um único terminal — o Electron main process já contém todo o motor de
rastreamento/gestos/mouse, sem processo filho separado.

```powershell
pnpm dev
```

O Electron abre a janela de configuração automaticamente na primeira execução.

Na primeira execução abre a janela de configuração: à esquerda ficam a
prévia da câmera, o botão persistente "Iniciar controle do mouse" e o botão
"Salvar configurações"; à direita, quatro abas.

- **Movimento**: não há mais gravação de extremos — o cursor se move de
  forma relativa à cabeça, como um mouse de verdade. Sliders ajustam esse
  movimento: sensibilidade horizontal e vertical (quanto o cursor anda
  para cada movimento da cabeça em cada eixo — a vertical costuma precisar
  ser maior, porque a cabeça se move menos nesse eixo), aceleração (deixa
  movimentos pequenos mais lentos e movimentos grandes mais rápidos, para
  mirar com precisão sem perder velocidade), limiar de movimento (ignora
  tremores menores que um certo número de pixels, pra ajudar o cursor a
  parar completamente) e quanto tempo esperar parado no mouse físico antes
  de retomar o controle pela cabeça. Um interruptor liga o clique por
  permanência (dwell click): com um slider ao lado ajustando o tempo, o
  clique esquerdo dispara sozinho quando o cursor fica parado sobre um
  elemento, sem precisar de gesto — desligado por padrão.
- **Gestos**: nove gestos, cada um com uma barra que enche conforme você se
  aproxima de dispará-lo. Escolha a
  ação de mouse de cada gesto e, no slider ao lado, por quanto tempo a
  expressão precisa ser segurada pra valer (padrão 400ms — bem acima de uma
  piscada natural, que dura ~100-150ms). Passar o mouse sobre uma linha
  destaca, na prévia da câmera, a região do rosto que dispara aquele gesto.
- **Extras**: liga ou desliga recursos opcionais. Um interruptor esconde o
  botão flutuante de teclado virtual — em alguns PCs o teclado touch do
  Windows não está disponível (o COM `ITipInvocation` não é registrado --
  erro `REGDB_E_CLASSNOTREG` no log do backend) e o botão nunca abre nada;
  desative-o aqui pra tirá-lo da tela. Outro interruptor esconde do mesmo
  jeito o botão de digitação por voz. Um terceiro liga ou desliga o
  registro de cliques em `clicks.log`. "Aparência do cursor" ajusta o
  tamanho da seta real do Windows (32 a 96px) e sua cor (branco, preto,
  personalizada, ou "mista", que inverte a cor do que está embaixo dela
  para nunca ficar invisível) — aplica na hora; ao fechar o app o cursor
  original do Windows volta, e o tema só reaparece no próximo início se
  você tiver clicado em "Salvar configurações".
- **Ajuda**: o mesmo resumo de uso e atalhos, dentro da própria janela.

Quando terminar de ajustar o movimento e mapear os gestos, clique em "Iniciar
controle do mouse" — a janela some e o controle do mouse fica ativo em
background, já com os ajustes atuais. Isso não grava nada em disco: Iniciar,
Parar e fechar a janela (X) nunca salvam sozinhos, só aplicam ou não o
controle. Pra manter os ajustes salvos pra próxima vez que abrir o app,
clique em "Salvar configurações".

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

Um par de círculos flutuantes -- teclado (azul) e microfone (vermelho) --
fica sempre visível por cima de tudo, agrupado numa única janelinha no
canto inferior direito por padrão -- inclusive enquanto a config está
aberta, já que abrir a config pausa o controle pela cabeça. Os dois se
movem juntos: arrastar qualquer um dos dois (mouse físico, trackpad, ou o
cursor controlado pela cabeça) move o par inteiro, mantendo-os sempre
próximos; a posição escolhida fica salva entre sessões. Um botão em
"Redefinir posição do teclado/microfone" na janela de configuração devolve
o par pro canto padrão a qualquer momento.

Clicar no ícone de teclado (funciona pelo cursor controlado pela cabeça
também) abre o teclado touch do Windows -- não o antigo `osk.exe`, porque
esse exige elevação e não responde a clique sintético; abre no modo
flutuante compacto em vez de ocupar a largura toda da tela. Clicar no
ícone de microfone ativa a digitação por voz nativa do Windows (o mesmo
recurso do atalho Win+H) no campo de texto que estiver em foco -- pra
quem precisa transcrever fala em vez de digitar.

Cada clique disparado por gesto mostra um pulso azul na posição do cursor,
pra confirmar visualmente que o clique aconteceu — útil porque piscar ou
levantar a sobrancelha não tem o retorno tátil de um clique físico.

Todo clique também fica registrado em `clicks.log` (data, gesto, ação,
posição e a janela em foco), rotacionado automaticamente pra não crescer
sem limite; nunca é enviado pra lugar nenhum, e pode ser desligado na aba
Movimento.

Config salvo em `config.json` e histórico de cliques em `clicks.log`,
ambos em `apps/desktop/` (ignorados pelo git), já que é de lá que o
Electron roda (`apps/desktop` é o cwd do processo). Quem tinha um
`config.json` na raiz do projeto de antes dessa migração pro monorepo
precisa movê-lo pra `apps/desktop/`, senão o app trata como primeira
execução.

## Testes

```powershell
pnpm test
```

Cobre a lógica pura (motor de gestos, poda de pontos e curva de aceleração,
cessão de controle ao mouse físico, log de cliques, load/save de config)
sem precisar de câmera real. Câmera, bandeja, atalhos e a aparência visual
do pulso exigem checklist manual (ver spec).

## Build do instalador (.exe)

```powershell
pnpm dist
```

Empacota o Electron (motor de rastreamento incluído) num instalador único
via `electron-builder`.

O instalador fica em `apps/desktop/release/FaceMesh Mouse Setup <versão>.exe`.
Pontos de atenção:

- Primeira execução é mais lenta (carrega o modelo do MediaPipe e o WASM
  do opencv.js).
- Instalador não assinado → Windows SmartScreen avisa no primeiro uso.
- Precisa conceder permissão de câmera do Windows ao app na primeira vez.
