![HoraInfo — monitoramento de switches no Home Assistant](custom_components/ha_oraco/brand/logo.png)

# HoraInfo

**Monitoramento local de switches Horaco/OEM gerenciáveis no Home Assistant**

[![Validação automatizada](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml)
[Licença MIT](LICENSE) · [Histórico de alterações](https://github.com/lucaslucian/ha_oraco/commits/main)

[**Adicionar o repositório ao HACS**](https://my.home-assistant.io/redirect/hacs_repository/?owner=lucaslucian&repository=ha_oraco&category=integration)


> [!IMPORTANT]
> **Versão atual: 0.4.35 · Experimental · Somente leitura.**
> A integração já está sendo utilizada com um switch real e coleta dados no Home Assistant. Isso **não equivale a homologação universal**: o firmware e o HTML CGI variam entre modelos. Consulte as [limitações](#limitações-conhecidas) antes de instalar.

## O que é o HoraInfo?

O **HoraInfo** é uma integração personalizada para acompanhar switches Horaco e equipamentos OEM compatíveis com a interface HTTP/CGI utilizada por alguns switches gerenciáveis Realtek. Reúne dados de portas, tráfego, transceptor óptico, tabela MAC, VLANs e proteções em um **painel próprio na barra lateral**, além de disponibilizar **sensores e sensores binários nativos** do Home Assistant.

A comunicação é local e a integração é destinada a **monitoramento**, não ao gerenciamento da configuração do switch. Não modifica VLANs, isolamento de portas, STP, firmware ou parâmetros administrativos.

O nome apresentado é **HoraInfo**, mas o domínio interno da integração permanece `ha_oraco` para preservar a compatibilidade com instalações existentes. O endereço do repositório também permanece `lucaslucian/ha_oraco`.

## Funcionalidades

| Área | Recursos disponíveis |
| --- | --- |
| **Visão geral** | Portas ativas, taxas atuais RX/TX, picos observados, firmware e visão das interfaces |
| **Portas** | Estado do link, velocidade negociada, duplex, contadores e taxas RX/TX; modal com histórico e MACs por porta |
| **Histórico de tráfego** | Seleção do switch ou de uma porta; períodos de 1 h, 6 h, 12 h, 1, 3, 5, 7, 15 e 30 dias; gráfico de taxas e barras de volume diário |
| **SFP+ / DDMI** | Presença, identificação e medidas atuais; histórico de temperatura com mínima, máxima e média, selecionável de 1 hora a 30 dias |
| **Inventário MAC** | MACs aprendidos, porta, VLAN, fabricante e datas; filtros por porta, VLAN e fabricante; apelidos personalizados |
| **Mapa de rede** | Nós individuais por MAC, posições arrastáveis e salvas, nomes personalizados e equipamentos intermediários documentados manualmente |
| **VLANs** | Informações de associação e modo das portas (access, trunk ou hybrid), VLAN nativa e listas tagged/untagged quando expostas pelo firmware |
| **Proteções** | Consulta de isolamento, STP/RSTP global e por porta, Storm Control e agregação de portas |
| **Outros diagnósticos** | IGMP, DHCP Snooping, Jumbo Frames, saúde das consultas HTTP e estado da base de fabricantes |
| **Home Assistant** | Sensores e sensores binários nativos, descoberta de interfaces e painel acessível a administradores |

Na versão 0.4.28, o painel recebeu ajustes de contraste, espaçamento, responsividade e legibilidade de tabelas, cartões, modais e gráficos. Os gráficos de tráfego apresentam horários proporcionais às datas efetivas das amostras e rótulos no eixo temporal. Os gráficos térmicos e ópticos exibem média, mínima e máxima por amostra ao apontar para os marcadores. O painel respeita a preferência do sistema por movimento reduzido.

O painel separa **estado atual** e **histórico**. As portas podem ser abertas em um modal com detalhes operacionais, contadores, tráfego histórico e MACs observados. Gráficos de tráfego exibem valores exatos ao apontar para os pontos de medição. Os snapshots podem ser comparados campo a campo (antes/depois), em vez de mostrar apenas a estrutura completa. O modo de exibição compacta e o período padrão de tráfego podem ser salvos. As seções compatíveis possuem um visualizador de alterações em janela modal, organizado por dia, com verificações registradas e detalhes das mudanças.

### Mapa e identificação dos dispositivos

Cada endereço MAC observado na tabela de encaminhamento é representado individualmente. Os nós podem ser arrastados; as posições e os apelidos são armazenados no Home Assistant. Também é possível cadastrar equipamentos intermediários associados manualmente a uma porta e associar MACs conhecidos a esses equipamentos. As ligações informadas pelo usuário aparecem tracejadas, distintas das observações reais da tabela MAC. Essas associações são indicadas de forma distinta e **não são detecção física automática**. O HoraInfo pode apresentar o **nome conhecido** do registro, ou o **fabricante inferido pelo prefixo OUI**, ao lado do MAC.

**Fabricante não é nome de host:** a base IEEE/OUI não revela automaticamente nomes como `Notebook`, `OpenWrt` ou `HomeAssistant`. Também não há descoberta física por LLDP implementada. O mapa indica **em qual porta o switch aprendeu cada MAC**, mas não comprova que o dispositivo está conectado diretamente à porta — outros switches ou equipamentos podem existir no caminho.

### Sensores e classificação de MACs

Há sensores de informações do equipamento, quantidade de portas ativas, métricas ópticas, dados por porta e contagens de MACs.

Os sensores **MACs privados (atuais)** e **MACs privados (histórico)** representam endereços com o **bit de administração local** ativado. Um resultado igual a zero pode ser legítimo e não significa que não existam dispositivos na LAN. A contagem histórica utiliza o inventário persistido.

### Proteção contra contadores anômalos

As taxas RX/TX e os volumes acumulados são calculados a partir das diferenças entre contadores de bytes fornecidos pelo switch. O HoraInfo rejeita leituras inválidas, contadores reiniciados, possíveis rollovers, intervalos longos sem observação e variações incompatíveis com a capacidade da porta. RX e TX são avaliados separadamente.

**Quando uma das direções RX/TX está indisponível, o registro de taxa conjunto é descartado, em vez de gravar um zero artificial; os volumes por contador são avaliados independentemente. Tráfego durante períodos sem observação não é reconstruído nem estimado.** Após uma interrupção, pode haver lacunas no volume contabilizado. O objetivo é impedir picos artificiais e somas incorretas.

## Instalação

### Pelo HACS

Use **Adicionar ao HACS** no início desta página. Caso o redirecionamento não cadastre automaticamente o projeto:

1. Abra o **HACS** na sua instalação do Home Assistant.
2. Adicione `https://github.com/lucaslucian/ha_oraco` como **repositório personalizado**, categoria **Integração**.
3. Instale o **HoraInfo** e reinicie o Home Assistant.
4. Abra **Configurações → Dispositivos e serviços → Adicionar integração → HoraInfo**.
5. Informe **IP ou host, porta HTTP, usuário e senha** do switch.
6. Abra **HoraInfo** na barra lateral.

O HoraInfo é disponibilizado como **repositório personalizado do HACS**; o botão não significa que esteja incluído no catálogo oficial do HACS.

### Instalação manual (sem HACS)

1. Copie a pasta `custom_components/ha_oraco` deste repositório para `<config>/custom_components/ha_oraco` no Home Assistant.
2. Reinicie o Home Assistant.
3. Adicione a integração em **Configurações → Dispositivos e serviços**, como descrito acima.

Mantenha a pasta **`ha_oraco`** mesmo que a interface mostre o nome HoraInfo. Na instalação manual, as atualizações devem ser aplicadas manualmente.

### Atualização de instalações existentes

Atualize os arquivos pelo HACS ou pelo método manual utilizado, **reinicie o Home Assistant** e recarregue o navegador (`Ctrl + F5`) se o painel ainda mostrar a interface antiga. Mantenha um backup do diretório de configuração, especialmente do banco SQLite e do armazenamento local, antes de grandes atualizações.

## Coleta e armazenamento

O HoraInfo utiliza consultas HTTP periódicas. Os intervalos abaixo são os atualmente definidos no código; a coleta rápida pode ser ajustada nas opções da integração.

| Dados | Intervalo padrão |
| --- | --- |
| Informações de portas e contadores de tráfego | 30 s |
| SFP+ / transceptor | 60 s |
| Tabela MAC | 120 s |
| DHCP Snooping e IGMP | 5 min |
| VLANs, isolamento, STP, Storm Control e agregação | 10 min |
| Jumbo Frames | 60 min |
| Metadados estáticos do dispositivo | Publicação aproximadamente a cada 60 min; `/info.cgi` é consultado também no ciclo rápido |

As principais páginas utilizadas incluem `/info.cgi`, `/port.cgi?page=stats`, `/transceiver.cgi` e `/mac.cgi?page=fwd_tbl`, além dos endpoints específicos de VLANs e proteções.

A integração **reutiliza a sessão autenticada** enquanto válida e tenta recuperar sessões expiradas. POST é usado no login e na paginação de leitura da tabela MAC, sem comandos de configuração.

### Retenção e histórico SQLite

As preferências de interface, apelidos, posições do mapa e limites ópticos ficam no armazenamento local do Home Assistant (`ha_oraco_dashboard_preferences`), separadas das leituras. Na aba **Sistema → Armazenamento SQLite** é possível consultar o tamanho efetivo do arquivo, espaço livre interno reutilizável, linhas por tabela e, quando o SQLite suporta `dbstat`, a ocupação aproximada das próprias tabelas. O resumo é do banco completo, compartilhado pelos switches cadastrados. Uma simulação de retenção completa (nove portas físicas, mais totalização, coleta de 30 s) ocupou cerca de **34 MiB** para as principais séries e seus índices; não é uma previsão garantida nem medição do seu ambiente. O inventário MAC não tem retenção automática e as alterações dependem da atividade/configuração. O SQLite normalmente reutiliza páginas livres sem reduzir imediatamente o tamanho físico do arquivo. O banco fica em `<config>/.storage/ha_oraco_history.db`. É um banco **SQLite local**; não requer servidor externo.

| Tipo de registro | Política implementada |
| --- | --- |
| Amostras detalhadas de tráfego | Aproximadamente 48 horas |
| Médias e picos de tráfego em blocos de 5 minutos | 30 dias |
| Temperatura SFP+ (média, mínima e máxima em blocos de 5 minutos) | 30 dias |
| Tensão, corrente e potências ópticas RX/TX (média, mínima e máxima em blocos de 5 minutos) | 7 dias |
| Volumes RX/TX consolidados por dia e por interface | 30 dias |
| Resumos diários de verificações e snapshots de alterações | 90 dias |
| Inventário MAC: primeira/última observação, porta, VLAN e fabricante | Histórico persistente; sem retenção temporal automática definida no código |

A versão 0.4.31 corrige a passagem de parâmetros opcionais das requisições WebSocket de histórico; só o histórico óptico envia a identificação de uma métrica. O histórico de tráfego permite selecionar **1, 6 ou 12 horas; 1, 3, 5, 7, 15 ou 30 dias**. Volumes são derivados de **diferenças válidas dos contadores**, não da simples soma de velocidades instantâneas.

O modal de snapshots carrega até 180 eventos mais recentes por categoria e sinaliza quando existem mais eventos; os totais diários continuam refletindo o histórico retido no banco. Os snapshots de VLANs, transceptores e proteções são gravados quando há alteração de dados **exceto temperatura SFP+**, que é tratada como telemetria independente, enquanto os resumos diários registram a última análise e a quantidade de verificações. A consulta é apresentada por dia em **janela modal**. A temperatura SFP+ é registrada separadamente a cada coleta válida e consolidada em intervalos de cinco minutos, com gráfico e extremos por 30 dias. Tensão, corrente do laser e potências ópticas RX/TX possuem quatro gráficos independentes com mínimo, média e máximo, períodos selecionáveis de 1 hora a 7 dias e retenção de sete dias. Alterações em temperatura, tensão, corrente do laser e potências RX/TX, isoladamente, não geram eventos de configuração. A série temporal específica de temperatura permanece no SQLite por 30 dias. Eventos importantes como presença/ausência do módulo, perda de sinal, mudança de identificação óptica e alterações em VLAN, isolamento ou STP continuam sendo auditados. Leituras SFP anteriores à implantação da série não são reconstruídas integralmente a partir de snapshots antigos.

Os dados antigos armazenados antes da instalação da funcionalidade de histórico não podem ser reconstruídos retroativamente. O HoraInfo possui procedimentos de migração do histórico compatível já existente.

### Fabricantes OUI

A integração tenta atualizar arquivos IEEE **MA-L, MA-M e MA-S**, mantém cache local e reclassifica identidades conhecidas quando novos prefixos são obtidos. Caso as fontes IEEE não respondam, há uma tentativa alternativa por espelho público de dados OUI, cuja cobertura pode ser menor.

Os indicadores ópticos podem utilizar limites personalizados por equipamento, salvos no Home Assistant. **Esses valores são definidos pelo usuário, não são limites certificados automaticamente para o transceptor.** A seção **Sistema → Base IEEE de fabricantes** permite verificar quantidade de prefixos disponíveis, última atualização e eventuais falhas. Um MAC pode continuar sem fabricante por indisponibilidade da base, ausência de correspondência ou por ser um endereço administrado localmente.

## Compatibilidade e limitações conhecidas

- **Experimental:** o projeto é utilizado com um switch real, mas não foi homologado em todos os equipamentos Horaco/OEM nem nas diferentes versões de firmware.
- **HTML CGI variável:** algumas páginas apresentam marcação HTML incorreta. Os parsers incluem tratamento para formatos já observados, mas outras variantes podem exigir ajustes.
- **Somente leitura:** não inclui ações de reboot, reset, atualização de firmware, mudança de VLAN, isolamento, STP ou outros parâmetros.
- **SFP+:** disponibilidade e precisão dos dados dependem do firmware, do módulo e da resposta da página óptica. Ausência de potência óptica **não implica necessariamente ausência física do módulo**.
- **Topologia:** não descobre automaticamente enlaces físicos ou nomes de host por LLDP, DHCP ou mDNS. Exibe evidências provenientes da tabela MAC e permite anotações manuais claramente identificadas. As posições salvas são preferências visuais, não medições de rede.
- **VLANs:** não garante a descoberta de todas as configurações de PVID e recursos avançados do switch.
- **Alertas:** limites ópticos e alertas avançados ainda não estão implementados.
- **Ícones:** apesar de haver arquivos locais de marca em `custom_components/ha_oraco/brand/`, o HACS e a entidade de atualização podem continuar exibindo *Icon not available* mesmo com ícones locais válidos, devido à resolução de imagens do HACS por serviço antigo. Isso não indica necessariamente um problema de cache ou ausência dos arquivos. Verifique a imagem diretamente em Configurações → Dispositivos e serviços; o comportamento do HACS depende de atualização no próprio HACS.
- **Histórico:** em falhas de coleta ou reinicializações de contadores, pode haver intervalos não contabilizados; a integração não inventa valores para preencher essas lacunas.

Para investigar leituras ausentes, utilize **HoraInfo → Sistema → Saúde das consultas**. Ali é possível distinguir falhas HTTP, erros de interpretação do HTML e problemas de gravação do histórico.

## Segurança e privacidade

- Monitora o switch na rede local, sem expor endpoints de administração publicamente.
- O gerenciamento web desses equipamentos pode utilizar **HTTP sem TLS**; mantenha o switch em rede de administração confiável.
- Credenciais permanecem na configuração da integração do Home Assistant; o SQLite do HoraInfo **não armazena a senha do switch**.
- Os dados de MAC e histórico ficam na instalação local do Home Assistant. A consulta de fabricantes baixa **bases OUI**, sem enviar o inventário MAC individual à IEEE.
- O painel e os comandos WebSocket do dashboard/histórico exigem **usuário administrador**.
- Inclua `.storage/ha_oraco_history.db` e os dados pertinentes de `.storage/` nos backups do Home Assistant.

## Desenvolvimento e testes

O repositório possui testes automatizados de parsers, páginas CGI reais e malformadas, sessão HTTP, contadores de tráfego, SQLite, inventário e componentes do painel. O fluxo [Offline validation](https://github.com/lucaslucian/ha_oraco/actions/workflows/offline-tests.yml) executa **pytest, validação JavaScript/JSON, Hassfest e verificação HACS**. O indicador no topo reflete o resultado publicado pelo GitHub Actions; uma execução bem-sucedida não substitui os testes no hardware real.

Para executar localmente:

```bash
python -m pip install beautifulsoup4 aiohttp pytest
python -m compileall -q custom_components/ha_oraco devtools tests
python -m pytest -q tests/
node --check custom_components/ha_oraco/frontend/ha-oraco-panel.js
```

O simulador de desenvolvimento pode ser iniciado com:

```bash
python devtools/mock_switch.py --ports 10 --port 8089
```

O simulador escuta localmente e **não reproduz integralmente** o comportamento dos firmwares reais.

Para bugs e sugestões, utilize as [issues do GitHub](https://github.com/lucaslucian/ha_oraco/issues). Ao relatar problemas, informe a versão da integração, o modelo e o firmware do switch e os diagnósticos do painel, **sem compartilhar senhas ou cookies de autenticação**.

## Licença e créditos

Distribuído sob a [licença MIT](LICENSE).

Inspirado em [switch-dashboard](https://github.com/byte4geek/switch-dashboard) e [horaco_switch_ha](https://github.com/gtrancillo/horaco_switch_ha).

<sub>Partes do desenvolvimento e da documentação tiveram assistência de inteligência artificial. As funcionalidades e os limites de compatibilidade devem ser verificados em cada ambiente.</sub>


### Histórico, diagnóstico de erros e OUI (0.4.32)

A interface mostra erros WebSocket com código e mensagem legíveis (em vez de `[object Object]`) e permite tentar novamente a consulta de tráfego. O painel de snapshots exibe listas aninhadas como itens, sem converter objetos para texto bruto. A entrada de limites ópticos aceita números negativos (por exemplo, -40 e -10 dBm) e deixa os botões de configuração separados dos valores. As informações de OUI distinguem o **último download bem-sucedido** da **última tentativa** (mesmo quando todas as fontes falharam), com datas e estado das fontes persistidos no Home Assistant após reinicializações. Se o gráfico histórico continuar sem dados, consulte a mensagem de erro detalhada e a seção Sistema → Armazenamento SQLite antes de presumir que a coleta foi perdida.


### Auditoria de regressão (0.4.33)

- Corrigida a persistência de contadores não representáveis pelo inteiro **assinado** de 64 bits do SQLite; valores acima desse limite deixam de ser gravados como baseline, evitando exceções e preservando as amostras de velocidade válidas.
- Quando a coleta do endpoint SFP+ falha, as medições ópticas deixam de ser expostas como *atuais*; os registros históricos persistidos não são apagados.
- Ampliados os testes para tentativas OUI malsucedidas, preservação do cache existente, restauração de data e status após reinicialização e limite do contador SQLite.
- O CI agora executa também um teste **JavaScript em tempo de execução** que abre todas as abas e modais de porta e snapshots com dados simulados, além da anterior checagem de sintaxe. Isso melhora a cobertura, mas não substitui testes de interface e sensores na instalação real do Home Assistant.

**Riscos ainda acompanhados:** inventário MAC histórico no SQLite sem limite de retenção, carregamento de apenas 180 eventos de snapshot por categoria (com aviso), variações desconhecidas do HTML OEM e possíveis falhas de renderização específicas do navegador/tema do Home Assistant. Nenhum dado MAC antigo foi excluído automaticamente.


### Limites ópticos negativos (0.4.34)

O ajuste manual dos limites RX/TX aceita dois extremos negativos em **qualquer ordem**: informar `-15` e `-25` resulta automaticamente em mínimo `-25 dBm` e máximo `-15 dBm`. São aceitos pontos ou vírgulas decimais e o sinal negativo Unicode. Essa configuração é uma faixa de referência do usuário, não um limite certificado para o módulo SFP+.


### Auditoria SFP+ sem ruído óptico (0.4.35)

A auditoria SFP+ passou de uma lista de campos excluídos para uma **lista explícita de dados de identificação e eventos relevantes**. Temperatura, tensão, corrente, potências RX/TX e outros campos DDMI desconhecidos do firmware nunca geram novos eventos de alteração de configuração. Os valores atuais continuam exibidos no painel e suas séries permanecem no SQLite (temperatura 30 dias; demais grandezas ópticas 7 dias). Presença, perda de sinal e troca/identificação do módulo ainda podem gerar eventos. A comparação com snapshots legados também aplica a mesma regra; os registros antigos já gravados não são apagados automaticamente para preservar dados históricos.
