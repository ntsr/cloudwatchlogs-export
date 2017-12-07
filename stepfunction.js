const app = require('./app')
const constants = app.constants()
const serviceName = constants.ServiceName
const lambdaArnPrefix = "arn:aws:lambda:"+constants.AwsRegion+":"+constants.AwsAccountId+":function:"+serviceName+"-"+constants.DeployStage+"-"
const definition = {
  "Comment": "A state machine that executes CloudWatchLogs.CreateExportTask for all LogGroups.",
  "StartAt": "Enqueue",
  "States": {
    "Enqueue": {
      "Type": "Task",
      "Resource": lambdaArnPrefix+"sfnEnqueue",
      "Next": "CreateExportTask"
    },
    "CreateExportTask": {
      "Type": "Task",
      "Resource": lambdaArnPrefix+"sfnCreateExportTask",
      "ResultPath": "$.taskId",
      "Next": "GetQueueStatus",
      "Retry": [
        {
          "ErrorEquals": ["States.ALL"],
          "IntervalSeconds": 1,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ]
    },
    "GetQueueStatus": {
      "Type": "Task",
      "Resource": lambdaArnPrefix+"sfnGetQueueStatus",
      "Next": "QueueComplete?",
      "ResultPath": "$.status",
      "Retry": [
        {
          "ErrorEquals": ["States.ALL"],
          "IntervalSeconds": 1,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ]
    },
    "QueueComplete?": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.status",
          "StringEquals": "FALSE",
          "Next": "CreateExportTask"
        },
        {
          "Variable": "$.status",
          "StringEquals": "TRUE",
          "Next": "FinalTask"
        }
      ],
      "Default": "QueueFailed"
    },
    "QueueFailed": {
      "Type": "Fail",
      "Cause": "CreateExportTasks Failed",
      "Error": "GetQueueStatus returned FAILED"
    },
    "FinalTask": {
      "Type": "Task",
      "Resource": lambdaArnPrefix+"sfnFinalTask",
      "End": true,
      "Retry": [
        {
          "ErrorEquals": ["States.ALL"],
          "IntervalSeconds": 1,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ]
    }
  }
}
module.exports.definition = () => {
  return JSON.stringify(definition)
}
