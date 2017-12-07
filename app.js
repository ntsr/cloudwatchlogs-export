var ConfigFile = require('config')
var config = ConfigFile.get('config')

const now = new Date();
const year = now.getFullYear();
const month = now.getMonth() + 1; // 0オリジン
const day = now.getDate();
const unixtime = now.getTime();

var constants = {
    ServiceName: config.serviceName,
    AwsRegion: config.region,
    AwsAccountId: config.accountId,
    DeployStage: config.stage,
    AwsProfile: config.profile,
    LogLevel: "INFO",
    ApiVersion: config.stage+"_"+year+month+day+"_"+unixtime,
}

module.exports = {
    constants: () => { return constants }
}
