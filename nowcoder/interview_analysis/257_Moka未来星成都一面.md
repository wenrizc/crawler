[查看原文](https://www.nowcoder.com/feed/main/detail/df6888d509cd47af9d43437bfe267bb7)

根据您提供的面试记录，以下是从中解析出的所有面试问题。为了确保不遗漏细节，部分包含多个知识点的提问已被拆分为独立问题：

**基础与JVM相关**
1. Java有哪些基本数据类型？
2. Java基本数据类型和包装类型，二者在JVM中的存储区别是什么？

**并发编程（JUC）**
3. synchronized 和 ReentrantLock 的区别是什么？
4. ReentrantLock 是怎么实现公平锁和非公平锁的？
5. 请讲一下 AQS（AbstractQueuedSynchronizer）的原理。
6. synchronized 锁是如何释放的？
7. 线程池的原理是什么？

**数据结构与集合框架**
8. 平时工作中用哪些数据结构？
9. HashSet 的底层数据结构是什么？
10. HashMap 的 put 流程是怎样的？
11. HashMap 是怎么比较 key 是否相同的？（涉及 `==` 和 `equals` 的区别）

**框架（Spring Boot）**
12. Spring Boot 的自动装配机制是什么？
13. 什么是 SPI 机制？

**数据库（MySQL）**
14. MySQL 的事务隔离级别有哪些？
15. MySQL 是怎么实现可重复读（Repeatable Read）的？
16. 什么是 MySQL 的当前读和快照读？
17. 哪些场景属于当前读？当前读是如何加锁的？
18. MVCC 视图是怎么保证哪些数据可以读、哪些不可读的？
19. MySQL 索引的存储结构是什么？

**中间件（Redis）**
20. Redis 的 IO 模型是什么？
21. Redis 的持久化策略有哪些？

**项目经历与HR面**
22. 在实习（或过往工作）中，遇到过比较难解决的问题是什么？
23. 关于你实现的监控功能，是怎么判断任务执行情况的？（注：面试官此处带有挑战性质，指出之前的实现可能并未真正实现该功能）
24. 上一家公司为什么离职？