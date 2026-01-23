from module.config.utils import get_os_reset_remain
from module.logger import logger
from module.os.map import OSMap


class OpsiObscure(OSMap):
    def notify_push(self, title, content):
        """
        发送推送通知（智能调度功能）
        
        Args:
            title (str): 通知标题（会自动添加实例名称前缀）
            content (str): 通知内容
            
        Notes:
            - 仅在启用智能调度时生效
            - 需要在配置中设置 Error_OnePushConfig 才能发送推送
            - 使用 onepush 库发送通知到配置的推送渠道
            - 标题会自动格式化为 "[Alas <实例名>] 原标题" 的形式
        """
        # 检查是否启用智能调度
        if not self.config.OpsiScheduling_EnableSmartScheduling:
            return
        # 检查是否启用推送大世界相关邮件
        if not self.config.OpsiGeneral_NotifyOpsiMail:
            return
            
        # 检查是否配置了推送
        push_config = self.config.Error_OnePushConfig
        if not push_config or 'provider: null' in push_config or 'provider:null' in push_config:
            logger.warning("推送配置未设置或 provider 为 null，跳过推送。请在 Alas 设置 -> 错误处理 -> OnePush 配置中设置有效的推送渠道。")
            return
        
        # 获取实例名称并格式化标题
        instance_name = getattr(self.config, 'config_name', 'Alas')
        if title.startswith('[Alas]'):
            formatted_title = f"[Alas <{instance_name}>]{title[6:]}"
        else:
            formatted_title = f"[Alas <{instance_name}>] {title}"
            
        try:
            from module.notify import handle_notify as notify_handle_notify
            success = notify_handle_notify(
                self.config.Error_OnePushConfig,
                title=formatted_title,
                content=content
            )
            if success:
                logger.info(f"✓ 推送通知成功: {formatted_title}")
            else:
                logger.warning(f"✗ 推送通知失败: {formatted_title}")
        except Exception as e:
            logger.error(f"推送通知异常: {e}")
    
    def _get_operation_coins_return_threshold(self):
        """
        Calculate the yellow coin return threshold for switching back to CL1.
        
        Returns:
            tuple: (return_threshold, cl1_preserve) or (None, cl1_preserve) if disabled
                - return_threshold: The threshold value, or None if check is disabled (value is 0)
                - cl1_preserve: The CL1 preserve value (cached for reuse)
        """
        if not self.is_cl1_enabled:
            return None, None
        
        # Get and cache CL1 preserve value
        cl1_preserve = self.config.cross_get(
            keys='OpsiHazard1Leveling.OpsiHazard1Leveling.OperationCoinsPreserve',
            default=100000
        )
        
        # Get OperationCoinsReturnThreshold from common config
        return_threshold_config = self.config.cross_get(
            keys='OpsiScheduling.OpsiScheduling.OperationCoinsReturnThreshold',
            default=None
        )
        
        # If value is 0, disable yellow coin check
        if return_threshold_config == 0:
            return None, cl1_preserve
        
        # If value is None, use default (equal to cl1_preserve, resulting in 2x threshold)
        if return_threshold_config is None:
            return_threshold_config = cl1_preserve
        
        # Calculate final threshold: CL1 preserve + return threshold
        return_threshold = cl1_preserve + return_threshold_config
        
        return return_threshold, cl1_preserve
    
    def _check_yellow_coins_and_return_to_cl1(self, context="循环中"):
        """
        Check if yellow coins are sufficient and return to CL1 if so.
        
        Args:
            context: Context string for logging (e.g., "任务开始前", "循环中")
        
        Returns:
            bool: True if returned to CL1, False otherwise
        """
        if not self.is_cl1_enabled:
            return False
        
        return_threshold, cl1_preserve = self._get_operation_coins_return_threshold()
        
        # If check is disabled (return_threshold is None), skip
        if return_threshold is None:
            logger.debug('OperationCoinsReturnThreshold 为 0，跳过黄币检查')
            return False
        
        yellow_coins = self.get_yellow_coins()
        logger.info(f'【{context}黄币检查】黄币={yellow_coins}, 阈值={return_threshold}')
        
        if yellow_coins >= return_threshold:
            logger.info(f'黄币充足 ({yellow_coins} >= {return_threshold})，切换回侵蚀1继续执行')
            self.notify_push(
                title="[Alas] 隐秘海域 - 黄币充足",
                content=f"黄币 {yellow_coins} 达到阈值 {return_threshold}\n切换回侵蚀1继续执行"
            )
            with self.config.multi_set():
                # 禁用所有黄币补充任务的调度器，防止被重新调度
                self.config.cross_set(keys='OpsiObscure.Scheduler.Enable', value=False)
                self.config.cross_set(keys='OpsiAbyssal.Scheduler.Enable', value=False)
                self.config.cross_set(keys='OpsiStronghold.Scheduler.Enable', value=False)
                self.config.cross_set(keys='OpsiMeowfficerFarming.Scheduler.Enable', value=False)
                self.config.task_call('OpsiHazard1Leveling')
            self.config.task_stop()
            return True
        
        return False
    
    def _try_other_coin_tasks(self):
        """
        尝试调用其他黄币补充任务
        使用固定顺序：隐秘海域 -> 深渊海域 -> 塞壬要塞 -> 短猫相接
        """
        # 定义所有黄币补充任务的固定顺序
        all_coin_tasks = ['OpsiObscure', 'OpsiAbyssal', 'OpsiStronghold', 'OpsiMeowfficerFarming']
        current_task = 'OpsiObscure'
        
        # 找到当前任务在列表中的位置
        try:
            current_index = all_coin_tasks.index(current_task)
        except ValueError:
            current_index = -1
        
        # 从当前任务的下一个开始尝试
        for i in range(current_index + 1, len(all_coin_tasks)):
            task = all_coin_tasks[i]
            if self.config.is_task_enabled(task):
                logger.info(f'尝试调用黄币补充任务: {task}')
                self.config.task_call(task)
                return
        
        # 如果后面的任务都不可用，尝试前面的任务（但跳过自己）
        for i in range(0, current_index):
            task = all_coin_tasks[i]
            if self.config.is_task_enabled(task):
                logger.info(f'尝试调用黄币补充任务: {task}')
                self.config.task_call(task)
                return
        
        # 如果所有任务都不可用，返回侵蚀1
        logger.warning('所有黄币补充任务都不可用，返回侵蚀1')
        self.config.task_call('OpsiHazard1Leveling')
        self.config.task_stop()
    
    def clear_obscure(self):
        """
        Raises:
            ActionPointLimit:
        """
        logger.hr('OS clear obscure', level=1)
        self.cl1_ap_preserve()
        if self.config.OpsiObscure_ForceRun:
            logger.info('OS obscure finish is under force run')

        result = self.storage_get_next_item('OBSCURE', use_logger=self.config.OpsiGeneral_UseLogger,
                                            skip_obscure_hazard_2=self.config.OpsiObscure_SkipHazard2Obscure)
        if not result:
            # No obscure coordinates - 禁用任务
            logger.info('隐秘海域没有可执行内容，禁用任务')
            with self.config.multi_set():
                self.config.cross_set(keys='OpsiObscure.Scheduler.Enable', value=False)
                # 如果是因为黄币不足而启用的，尝试其他黄币补充任务
                if self.is_cl1_enabled and self.config.OpsiScheduling_EnableSmartScheduling:
                    yellow_coins = self.get_yellow_coins()
                    cl1_preserve = self.config.cross_get(
                        keys='OpsiHazard1Leveling.OpsiHazard1Leveling.OperationCoinsPreserve',
                        default=100000
                    )
                    if yellow_coins < cl1_preserve:
                        logger.info(f'黄币不足 ({yellow_coins} < {cl1_preserve})，尝试其他黄币补充任务')
                        self._try_other_coin_tasks()
                        return
            self.config.task_stop()
            return

        self.config.override(
            OpsiGeneral_DoRandomMapEvent=False,
            HOMO_EDGE_DETECT=False,
            STORY_OPTION=0,
        )
        self.zone_init()
        self.fleet_set(self.config.OpsiFleet_Fleet)
        self.os_order_execute(
            recon_scan=True,
            submarine_call=self.config.OpsiFleet_Submarine)
        self.run_auto_search(rescan='current')

        self.map_exit()
        self.handle_after_auto_search()

    def os_obscure(self):
        # ===== 任务开始前黄币检查 =====
        # 如果启用了CL1且黄币充足，直接返回CL1，不执行隐秘海域
        if self.is_cl1_enabled:
            return_threshold, cl1_preserve = self._get_operation_coins_return_threshold()
            if return_threshold is None:
                logger.info('OperationCoinsReturnThreshold 为 0，禁用黄币检查，仅使用行动力阈值控制')
            elif self._check_yellow_coins_and_return_to_cl1("任务开始前"):
                return
        
        while True:
            self.clear_obscure()
            # ===== 循环中黄币充足检查 =====
            # 在每次循环后检查黄币是否充足，如果充足则返回侵蚀1
            if self.is_cl1_enabled:
                if self._check_yellow_coins_and_return_to_cl1("循环中"):
                    return
            
            # 如果 ForceRun=False，任务完成后禁用任务
            if not self.config.OpsiObscure_ForceRun:
                logger.info('隐秘海域任务完成，禁用任务')
                self.config.cross_set(keys='OpsiObscure.Scheduler.Enable', value=False)
                break
            
            self.config.check_task_switch()
            continue
