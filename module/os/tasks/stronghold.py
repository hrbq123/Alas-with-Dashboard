from module.config.config import TaskEnd
from module.logger import logger
from module.os.fleet import BossFleet
from module.os.map import OSMap
from module.os_handler.assets import OS_SUBMARINE_EMPTY
from module.ui.page import page_os


class OpsiStronghold(OSMap):
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
                title="[Alas] 塞壬要塞 - 黄币充足",
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
        current_task = 'OpsiStronghold'
        
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
    
    def clear_stronghold(self):
        """
        Find a siren stronghold on globe map,
        clear stronghold,
        repair fleets in port.

        Raises:
            ActionPointLimit:
            TaskEnd: If no more strongholds.
            RequestHumanTakeover: If unable to clear boss, fleets exhausted.
        """
        logger.hr('OS clear stronghold', level=1)
        with self.config.multi_set():
            self.config.OpsiStronghold_HasStronghold = True
            self.cl1_ap_preserve()

            self.os_map_goto_globe()
            self.globe_update()
            zone = self.find_siren_stronghold()
            if zone is None:
                # No siren stronghold - 禁用任务
                logger.info('塞壬要塞没有可执行内容，禁用任务')
                with self.config.multi_set():
                    self.config.OpsiStronghold_HasStronghold = False
                    self.config.cross_set(keys='OpsiStronghold.Scheduler.Enable', value=False)
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

        self.globe_enter(zone)
        self.zone_init()
        self.os_order_execute(recon_scan=True, submarine_call=False)
        self.run_stronghold(submarine=self.config.OpsiStronghold_SubmarineEveryCombat)

        if self.config.OpsiStronghold_SubmarineEveryCombat:
            if self.zone.is_azur_port:
                logger.info('Already in azur port')
            else:
                self.globe_goto(self.zone_nearest_azur_port(self.zone))
        self.handle_fleet_repair_by_config(revert=False)
        self.handle_fleet_resolve(revert=False)
        
        # 检查是否还有更多要塞
        self.os_map_goto_globe()
        self.globe_update()
        next_zone = self.find_siren_stronghold()
        if next_zone is None:
            # 没有更多要塞 - 禁用任务
            logger.info('塞壬要塞没有更多可执行内容，禁用任务')
            self.config.OpsiStronghold_HasStronghold = False
            self.config.cross_set(keys='OpsiStronghold.Scheduler.Enable', value=False)
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

    def os_stronghold(self):
        # ===== 任务开始前黄币检查 =====
        # 如果启用了CL1且黄币充足，直接返回CL1，不执行塞壬要塞
        if self.is_cl1_enabled:
            return_threshold, cl1_preserve = self._get_operation_coins_return_threshold()
            if return_threshold is None:
                logger.info('OperationCoinsReturnThreshold 为 0，禁用黄币检查，仅使用行动力阈值控制')
            elif self._check_yellow_coins_and_return_to_cl1("任务开始前"):
                return
        
        while True:
            self.clear_stronghold()
            # ===== 循环中黄币充足检查 =====
            # 在每次循环后检查黄币是否充足，如果充足则返回侵蚀1
            if self.is_cl1_enabled:
                if self._check_yellow_coins_and_return_to_cl1("循环中"):
                    return
            self.config.check_task_switch()

    def os_sumbarine_empty(self):
        return self.match_template_color(OS_SUBMARINE_EMPTY, offset=(20, 20))

    def stronghold_interrupt_check(self):
        return self.os_sumbarine_empty() and self.no_meowfficer_searching()

    def run_stronghold_one_fleet(self, fleet, submarine=False):
        """
        Args
            fleet (BossFleet):
            submarine (bool): If use submarine every combat

        Returns:
            bool: If all cleared.
        """
        self.config.override(
            OpsiGeneral_DoRandomMapEvent=False,
            HOMO_EDGE_DETECT=False,
            STORY_OPTION=0
        )
        interrupt = [self.stronghold_interrupt_check, self.is_meowfficer_searching] if submarine else None
        # Try 3 times, because fleet may stuck in fog.
        for _ in range(3):
            # Attack
            self.fleet_set(fleet.fleet_index)
            try:
                self.run_auto_search(question=False, rescan=False, interrupt=interrupt)
            except TaskEnd:
                self.ui_ensure(page_os)
            self.hp_reset()
            self.hp_get()

            # End
            if self.get_stronghold_percentage() == '0':
                logger.info('BOSS clear')
                return True
            elif any(self.need_repair):
                logger.info('Auto search stopped, because fleet died')
                # Re-enter to reset fleet position
                prev = self.zone
                self.globe_goto(self.zone_nearest_azur_port(self.zone))
                self.handle_fog_block(repair=True)
                self.globe_goto(prev, types='STRONGHOLD')
                return False
            elif submarine and self.os_sumbarine_empty():
                logger.info('Submarine ammo exhausted, wait for the next clear')
                self.globe_goto(self.zone_nearest_azur_port(self.zone))
                return True
            else:
                logger.info('Auto search stopped, because fleet stuck')
                # Re-enter to reset fleet position
                prev = self.zone
                self.globe_goto(self.zone_nearest_azur_port(self.zone))
                self.handle_fog_block(repair=False)
                self.globe_goto(prev, types='STRONGHOLD')
                continue

    def run_stronghold(self, submarine=False):
        """
        All fleets take turns in attacking siren stronghold.
        Args:
            submarine (bool): If use submarine every combat

        Returns:
            bool: If success to clear.

        Pages:
            in: Siren logger (abyssal), boss appeared.
            out: If success, dangerous or safe zone.
                If failed, still in abyssal.
        """
        logger.hr(f'Stronghold clear', level=1)
        fleets = self.parse_fleet_filter()
        for fleet in fleets:
            logger.hr(f'Turn: {fleet}', level=2)
            if not isinstance(fleet, BossFleet):
                self.os_order_execute(recon_scan=False, submarine_call=True)
                continue

            result = self.run_stronghold_one_fleet(fleet, submarine=submarine)
            if result:
                return True
            else:
                continue

        logger.critical('Unable to clear boss, fleets exhausted')
        return False
