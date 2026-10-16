# Auditoria técnica HoraInfo — 16/10/2026 (v0.4.39)

Escopo: integração Home Assistant, leitura CGI, SQLite, WebSocket, frontend,
preferências, histórico de configurações e testes. Revisão estática acompanhada
de testes automatizados; testes com hardware OEM, navegador real e banco de
produção continuam necessários.

## Defeitos confirmados e corrigidos

| Área | Defeito | Correção |
| --- | --- | --- |
| SQLite / tráfego | Deltas válidos de contadores sem RX/TX bps não criavam bucket de cinco minutos. O total diário crescia, mas o total no período ficava subcontado. | Criar bucket de bytes com contagem de amostras de velocidade igual a zero; não inventar leitura de taxa nem pico. |
| Frontend / consultas | Pedidos simultâneos para o mesmo histórico disparavam múltiplas consultas WebSocket; recarregamentos apagavam dados visíveis durante a espera. | Compartilhar a requisição em andamento e preservar dados anteriores enquanto atualiza. |
| Frontend / amostras | Gráfico de tráfego da sessão não registrava timestamp por amostra, impossibilitando representar corretamente os horários. | Registrar timestamp UTC no momento da amostra. |
| Preferências | MACs com 17 caracteres contendo apenas separadores podiam passar na validação, inclusive em nós do mapa. | Validar exatamente seis octetos hexadecimais separados por dois-pontos. |
| Preferências | Falha ao gravar armazenamento deixava a preferência em memória como se estivesse salva. | Preparar cópia da estrutura e só atualizar a memória após sucesso na persistência. |
| STP / auditoria | Alterações de estado operacional, função da porta, custos calculados e eleição de ponte-raiz apareciam como mudanças de configuração. | Gravar somente parâmetros configurados para os snapshots STP e normalizar snapshots legados na comparação. |

Os dados antigos do SQLite **não são removidos** por essas correções. Contadores
de velocidade ausentes não são substituídos por zeros artificiais.

## Riscos e limites ainda abertos (não tratados como bugs reproduzidos)

1. **Identidade multi-switch por host/porta (médio):** o config flow distingue `host:porta`, enquanto unique IDs de entidades e IDs do registro de dispositivos usam apenas o host. Duas instâncias no mesmo endereço com portas HTTP diferentes podem conflitar. Corrigir requer uma migração do entity registry para não recriar entidades/automatizações existentes.
2. **HTML OEM (médio):** páginas CGI variam por modelo/firmware e podem fornecer dados malformados ou não suportados. Cobertura offline não comprova compatibilidade física.
3. **Dados antigos de auditoria (baixo):** snapshots operacionais STP gravados em versões anteriores permanecem preservados, mas não são apagados ou reescritos.
4. **Inventário MAC (baixo/médio):** tabela SQLite não tem expiração automática; é necessário definir política de retenção antes de excluir dados históricos dos usuários.
5. **Limite de histórico por categoria (baixo):** o painel consulta apenas 180 eventos recentes por categoria, com resumo diário indicando truncamento.
6. **Operação de rede (médio):** a autenticação HTTP do OEM e possíveis redirecionamentos ainda exigem testes na rede local, principalmente em diferentes firmwares. O gerenciamento do switch deve permanecer em segmento confiável.
7. **Cobertura (médio):** não há suíte E2E em navegador real contra Home Assistant real; testes em nós simulados não verificam layout de cada tema/celular nem todas as sessões de login.
8. **Exatidão de contadores parciais (baixo/médio):** quando só uma das direções de byte está disponível, a persistência de baseline de duas direções depende de ambas serem válidas; avaliar um modelo por direção antes de refatorar o armazenamento.

## Comparação com os projetos de inspiração

Fontes:
- https://github.com/byte4geek/switch-dashboard
- https://github.com/gtrancillo/horaco_switch_ha

| Funcionalidade observada nos projetos | HoraInfo | Encaminhamento |
| --- | --- | --- |
| Gráficos de tráfego e histórico acumulado | Implementado em SQLite | Melhorar diagnóstico e testes reais |
| Telemetria e identificação SFP+ | Implementado; coleta periódica | **Candidato:** botão DDMI sob demanda com rate-limit e somente GET |
| Filtros de MAC, anotações e topologia | Implementado parcialmente | **Candidato:** tabela MAC com altura ajustável e filtros salvos |
| Tamanho de fontes configurável | Ajustes de interface e compactação existentes | **Candidato:** escala de fonte acessível sem comprometer o tema HA |
| Documentação / explorador interativo de API | Documentação técnica dispersa | **Candidato:** guia de endpoints **somente leitura**, payloads e diagnósticos sanitizados |
| VLAN, isolamento, STP e proteção | Monitoramento e auditoria implementados | Fortalecer tratamento de firmwares OEM |
| DHCP/IGMP e jumbo frames | Leitura básica presente | **Candidato:** confiar/desconfiar por porta e detalhes IGMP **após** identificar CGI seguro |
| Entidades do Home Assistant por porta | Implementado | Migrar cuidadosamente a identidade host/porta |
| Topologia com dispositivos de infraestrutura | Visualização/anotações manuais | **Candidato:** classificação de infraestrutura explícita, sem deduzir enlaces físicos de uma tabela MAC |
| Proxmox OVS sobre SSH | Não implementado | Fora do escopo atual: ampliar exigiria conectores e modelo de autenticação próprios |
| Download de backup, reboot, atualização de firmware | Não implementado | **Fora do escopo deliberadamente:** projeto permanece somente leitura |

### Ordem sugerida para evoluções

1. Testes OEM reais e verificação visual por navegador/tema; saneamento de sessões.
2. Compatibilidade e migração segura de IDs caso haja switches com mesmo IP e portas distintas.
3. DDMI sob demanda, apenas leitura, com proteção contra excesso de consultas CGI.
4. Filtros e redimensionamento de tabelas MAC, escala tipográfica e documentação de API.
5. Novos dados DHCP/IGMP e classificação de topologia somente após validar parsers com HTML real.

Não confundir a ausência de um recurso opcional com falha de implementação.
Não propor escrita em firmware, reboot, backup de configuração ou configuração
de rede como melhoria automática.
