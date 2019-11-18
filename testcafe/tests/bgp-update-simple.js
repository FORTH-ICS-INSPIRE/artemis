import { Selector } from 'testcafe';

const util = require('util');
const exec = util.promisify(require('child_process').exec);

async function getToken() {
    const { stdout, stderr } = await exec('access_token=$(curl -k -X POST -H "Content-Type: application/json" -d \'{"username":"admin", "password":"admin123"}\' https://localhost/jwt/auth | jq -r .access_token)');
    console.log('stdout:', stdout);
    console.log('stderr:', stderr);
}

async function execQuery() {
    const { stdout, stderr } = await exec('curl -k -X POST -H "Content-Type: application/json" -H "Authorization":"Bearer $access_token" https://localhost/api/graphql -d \'{"query": "mutation insertHijack {insert_view_hijacks(objects: {active: true, comment: \"\", community_annotation: \"\", configured_prefix: \"10.0.0.0/8\", dormant: false, hijack_as: \"1\", ignored: false, key: \"1\", num_asns_inf: 10, num_peers_seen: 10, outdated: false, prefix: \"10.0.0.0/8\", resolved: false, seen: false, type: \"S|-|-|-\", under_mitigation: false, withdrawn: false, time_detected: \"2019-11-16T00:00:15.003573\"}) {returning {key}}}"}\'');
    console.log('stdout:', stdout);
    console.log('stderr:', stderr);
}

fixture `artemis`
    .page `https://localhost:8443`;

test('BGP Update Simple', async t => {
    await t
        .typeText(Selector('#email'), 'admin')
        .pressKey('tab')
        .typeText(Selector('#password'), 'admin123')
        .click(Selector('#submit'))
        .expect(Selector('li').withText('Clock').textContent).contains("Clock On 1/1")
        .expect(Selector('li').withText('Configuration').textContent).contains("Configuration On 1/1")
        .expect(Selector('li').withText('Database v.18').textContent).contains("Database v.18 On 1/1")
        .expect(Selector('li').withText('Detection').textContent).contains("Detection On 0/1")
        .expect(Selector('#modules_states').find('li').withText('Mitigation').textContent).contains("Mitigation On 0/1")
        .expect(Selector('#modules_states').find('li').withText('Monitor').textContent).contains("Monitor On 0/1")
        .expect(Selector('li').withText('Observer').textContent).contains("Observer On 1/1")
        .expect(Selector('#db_stat_value_monitored_prefixes').find('b').withText('1').textContent).eql("1")
        .expect(Selector('#db_stat_value_configured_prefixes').find('b').withText('3').textContent).eql("3")
        .expect(Selector('p').withText('ARTEMIS v.\'latest\'').textContent).eql("ARTEMIS v.'latest'")
        .click(Selector('#navbar_bgpupdates'))
        .expect(Selector('h3').withText('No BGP Updates to display').textContent).eql("No BGP Updates to display")
        .click(Selector('#navbar_hijacks'))
        .expect(Selector('h3').withText('No hijack alerts. Go grab a beer!').textContent).eql("No hijack alerts. Go grab a beer!")
        .click(Selector('a').withText('Admin'))
        .click(Selector('a').withText('System'))
        .expect(Selector('#module_monitor_instances_running').find('button').withText('Active 0/1').textContent).eql(" Active 0/1")
        .expect(Selector('#module_detection_instances_running').find('button').withText('Active 0/1').textContent).eql(" Active 0/1")
        .expect(Selector('#module_mitigation_instances_running').find('button').withText('Active 0/1').textContent).eql(" Active 0/1")
        .click(Selector('#system_modules_monitor').find('.slider.round'))
        .expect(Selector('button').withText('Active 1/1').textContent).eql(" Active 1/1", 'Monitor Module Active', {
            timeout: 3000
        })
        .click(Selector('#system_modules_detection').find('.slider.round'))
        .expect(Selector('button').withText('Active 1/1').textContent).eql(" Active 1/1", 'Detection Module Active', {
            timeout: 3000
        })
        .click(Selector('#system_modules_mitigation').find('.slider.round'))
        .expect(Selector('button').withText('Active 1/1').textContent).eql(" Active 1/1", 'Mitigation Module Active', {
            timeout: 3000
        })
        .click(Selector('#config_action'))
        .doubleClick(Selector('div').withText('1').nth(33).find('.CodeMirror-line'))
        .typeText(Selector('.CodeMirror.cm-s-default.CodeMirror-focused').find('div').find('textarea'), '# test config')
        .click(Selector('#config_action'))
        .click(Selector('a').withText('Admin'))
        .click(Selector('a').withText('System'))
        .expect(Selector('span').withText('# test config').find('.cm-comment').textContent).contains("# test config")
        .expect(Selector('#modules_states').find('li').withText('Mitigation').textContent).contains("Mitigation On 1/1")
        .click(Selector('a').withText('Admin'))
        .click(Selector('a').withText('System'))
        .click(Selector('#system_modules_mitigation').find('.slider.round'))
        .expect(Selector('#module_mitigation_instances_running').find('button').withText('Active 0/1').textContent).eql(" Active 0/1");
    },
    async token => {
        await getToken();
    },
    async query => {
        await execQuery();
    }
);
