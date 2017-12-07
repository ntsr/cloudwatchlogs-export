#!/usr/env python
# -*- coding: utf-8 -*-
"""
thx. https://blog.manabusakai.com/2016/08/cloudwatch-logs-to-s3/
thx. https://dev.classmethod.jp/cloud/aws/lambda-sqs-asynchronous-distributed-processing/
"""
import datetime
import time
import boto3
from boto3.session import Session
import json
from itertools import chain
import os
import logging
from Logger import CustomLogger as Logger
logging.setLoggerClass(Logger)
LOG = logging.getLogger(__name__)


s3_bucket_name = os.getenv('LOG_BUCKET_NAME') or 'log-bucket'
sqs_queue_name = os.getenv('SQS_NAME') or 'test'


class Queue:
    __resource = None
    __queue = None
    __session = None
    __queue_name = None

    def __init__(self, queue_name=sqs_queue_name, session=None):
        self.__queue_name = queue_name

        if isinstance(session, Session):
            self.__session = session

    def get_resource(self):
        if self.__session:
            self.__resource = self.__session.resource('sqs')

        if not self.__resource:
            self.__resource = boto3.resource('sqs')

        return self.__resource

    def get_queue(self):
        if not self.__queue:
            self.__queue = self.get_resource().get_queue_by_name(QueueName=self.__queue_name)

        return self.__queue

    def enqueue(self, data):
        body = json.dumps(data)
        response = self.get_queue().send_message(
            MessageBody=body
        )
        LOG.debug(response)
        return response['ResponseMetadata']['HTTPStatusCode'] == 200

    def dequeue(self, wait_time_sec=0, max_num=1, delete=False):
        messages = self.get_queue().receive_messages(
            MaxNumberOfMessages=max_num,
            WaitTimeSeconds=wait_time_sec
        )
        if delete:
            self.delete(messages)

        return messages

    def delete(self, messages):
        [m.delete() for m in messages]


class Logs:
    __client = None

    def __init__(self, session=None):
        if session:
            self.__client = session.client('logs')

        if not self.__client:
            self.__client = boto3.client('logs')

    def get_client(self):
        return self.__client

    def get_log_group_names(self):
        paginator = self.__client.get_paginator('describe_log_groups')
        pages = [page.get('logGroups') for page in paginator.paginate()]
        logGroups = list(chain.from_iterable(pages))
        logGroupNames = [lg.get('logGroupName') for lg in logGroups]
        # for name in logGroupNames:
        for name in logGroupNames:
            yield name


class LogsExportTask:
    logs = None
    storage = None

    def __init__(self, logs, bucket_name):
        self.logs = logs
        self.bucket_name = bucket_name

    def create(self, logGroupName, fromMsec, toMsec):
        destinationBucketName = self.bucket_name

        # LogGroupごとに、出力するbucketとObjectKeyのprefixを決める
        destinationPrefix = logGroupName.lstrip('/') + '/%s' % (datetime.date.today() - datetime.timedelta(days=1))
        LOG.info(destinationPrefix)

        response = self.logs.get_client().create_export_task(
            logGroupName=logGroupName,
            fromTime=fromMsec,
            to=toMsec,
            destination=destinationBucketName,
            destinationPrefix=destinationPrefix
        )
        return response


def get_from_timestamp():
    today = datetime.date.today()
    yesterday = datetime.datetime.combine(today - datetime.timedelta(days=1), datetime.time(0, 0, 0))
    timestamp = time.mktime(yesterday.timetuple())
    return int(timestamp)


def enqueue():
    """
    StepFunction内で実行され、対象となるLogGroupを抽出しsqsに登録する
    """
    logs = Logs()
    queue = Queue()

    from_tms = get_from_timestamp() * 1000
    to_tms = (from_tms + (60 * 60 * 24)) * 1000 - 1
    LOG.info('Timestamp: from_tms %s, to_tms %s' % (from_tms, to_tms))

    # 対象のCloudWatchLogsのLogGroupを取得する
    for name in logs.get_log_group_names():
        # SQSにタスクを登録する
        # logs:CreateExportTaskはアカウントごとに同時1つのアクティブなタスクしか許容されないため。
        data = {
            'logGroupName': name,
            'fromTime': from_tms,
            'toTime': to_tms
        }
        LOG.info(json.dumps(data))
        LOG.info(queue.enqueue(data))


def create_export_task():
    """
    StepFunction内で実行され、sqsからmessageを取得してExportTaskを登録する。
    成功すればsqsからmessageを削除する。
    失敗すれば例外を発行する。
    """
    taskMgr = LogsExportTask(logs=Logs(), bucket_name=s3_bucket_name)
    queue = Queue()

    messages = queue.dequeue()
    if len(messages) == 0:
        LOG.warning('no message!')
        return

    message = messages[0]

    body = json.loads(message.body)
    try:
        logGroupName = body['logGroupName']
        fromTime = body['fromTime']
        toTime = body['toTime']
        response = taskMgr.create(logGroupName=logGroupName, fromMsec=fromTime, toMsec=toTime)
        queue.delete([message])
    except Exception as e:
        LOG.debug(e.args)
        raise e

    LOG.debug(json.dumps(response))
    return response


def get_queue_status(taskId=None):
    """
    再度CreateExportTaskを行うべきかどうか判断する。
    以下がすべてtrueであればすべて処理が終了したものとみなす。
    * S3に当日のログが全て出力されている(=> 無限ループ注意)
    * 現在activeなタスクがない（describeExportTasksでstatusにRUNNINGのものが存在しない）

    → まずは簡単に、long pollingでqueueからメッセージが取得できるかどうかで判断することにする。
    """

    queue = Queue()
    if len(queue.dequeue(wait_time_sec=1)) > 0:
        """ まだキューが残っている """
        return 'FALSE'

    return 'TRUE'


def handle_launchFunctions(event, context):
    """
    cronで起動されStepFunctionを呼び出す
    """
    sfnClient = boto3.client('stepfunctions')
    arn = os.getenv('SFN_ARN')
    if not arn:
        raise Exception('no arn!')
    response = sfnClient.start_execution(
        stateMachineArn=arn
    )
    LOG.debug(response)


def handle_sfnEnqueue(event, context):
    LOG.debug(json.dumps(event))
    enqueue()
    return event


def handle_sfnCreateExportTask(event, context):
    LOG.debug(json.dumps(event))
    result = create_export_task()
    return result.get('taskId')


def handle_sfnGetQueueStatus(event, context):
    LOG.debug(json.dumps(event))
    taskId = event.get('taskId')
    result = get_queue_status(taskId=taskId)
    return result


def handle_sfnFinalTask(event, context):
    """
    タスク終了結果を通知する
    """
    LOG.debug(json.dumps(event))
    pass


if __name__ == '__main__':
    pass
