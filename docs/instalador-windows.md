# Instalador Windows

Na release 0.5.2 ou posterior, baixe **RevisorCelacanto-Instalador.exe**, execute e siga o assistente. O programa aparece no menu Iniciar como **Revisor Celacanto**. O atalho na área de trabalho é opcional. Não é necessário instalar Python ou executar como administrador.

O programa é instalado para o usuário atual em `%LOCALAPPDATA%\Programs\Celacanto\Revisor`. A biblioteca continua em `%LOCALAPPDATA%\Celacanto\AnalisadorRelatorios`, com histórico, documentos, critérios, exemplos e credenciais locais. O instalador não copia nem apaga essa biblioteca. Reinstalar substitui os arquivos do programa; desinstalar pelas Configurações do Windows remove o programa e seus atalhos, preservando os dados.

Quem usava o ZIP pode instalar e abrir pelo menu Iniciar. A biblioteca padrão é a mesma, portanto não é preciso importar tudo novamente. Se usava uma biblioteca personalizada com `--data-dir`, mantenha esse argumento no atalho; o instalador não adivinha caminhos personalizados. Feche a cópia portátil e passe a usar o atalho instalado para evitar abrir versões diferentes.

O botão **Atualizações** continua baixando o pacote ZIP oficial e substituindo os arquivos do programa instalado na pasta do usuário. Não é necessário reinstalar manualmente a cada versão. O ZIP continua disponível para quem prefere a versão portátil.

## Consumo e segurança

O instalador organiza a distribuição, mas o aplicativo instalado também executa um `.exe` e usa o mesmo motor. Não é uma otimização de CPU/RAM e não garante resolver lentidão. A aplicação não cria serviço, tarefa agendada ou inicialização automática com o Windows. A leitura de muitos PDFs e a preparação das imagens podem consumir recursos enquanto a revisão está em andamento.

O pacote ainda não possui assinatura digital: o instalador, por si só, não elimina alertas do SmartScreen ou detecções do AVG. Assinatura e análise de falso positivo são trabalhos separados; não é necessário desativar o antivírus como parte da instalação.

## Compilação e validação

Depois de gerar a pasta Windows com `build_windows.py`, execute:

```powershell
python installer/build_installer.py --dist dist --compiler "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"
```

O pipeline usa Inno Setup 6, compila o instalador, testa instalação silenciosa, atalho, abertura, reinstalação e desinstalação em runner descartável. Uma evidência externa à pasta instalada deve permanecer com o mesmo hash. O teste não é executado no computador do usuário. A publicação inclui instalador, ZIP portátil e SHA-256 dos dois arquivos.

O teste automatizado verifica o fluxo de empacotamento; não comprova desempenho em todo hardware nem ausência de bloqueios por antivírus.
